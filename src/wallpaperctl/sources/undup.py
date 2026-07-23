"""Library undup CLI — integrated wall-undup (Kitty preview + delete)."""

from __future__ import annotations

import base64
import io
import os
import select
import shutil
import sys
import time
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.sources.dedup import confidence_score, find_duplicate_groups

# Auto-delete only when confidence is clearly high (exact / near-exact matches).
# Lower scores still appear in scan output for review with plain --delete.
CONFIDENT_DELETE_MIN = 90.0


def supports_kitty_graphics() -> bool:
    if hasattr(supports_kitty_graphics, "_cached"):
        return supports_kitty_graphics._cached  # type: ignore[attr-defined]
    result = _detect_kitty_graphics()
    supports_kitty_graphics._cached = result  # type: ignore[attr-defined]
    return result


def _detect_kitty_graphics() -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        import termios

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        new = old[:]
        new[3] &= ~(termios.ICANON | termios.ECHO)
        new[6][termios.VMIN] = 0
        new[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, new)
        try:
            sys.stdout.buffer.write(b"\033_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA\033\\")
            sys.stdout.buffer.write(b"\033[c")
            sys.stdout.buffer.flush()
            resp = b""
            deadline = time.monotonic() + 0.3
            while time.monotonic() < deadline:
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    chunk = os.read(fd, 1024)
                    if chunk:
                        resp += chunk
                    else:
                        break
            return b"\033_G" in resp
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return False


def kitty_display(img_bytes: bytes, cols: int = 0) -> None:
    encoded = base64.b64encode(img_bytes).decode("ascii")
    first = True
    while encoded:
        chunk, encoded = encoded[:4096], encoded[4096:]
        m = 1 if encoded else 0
        if first:
            sys.stdout.write(f"\033_Ga=t,f=100,i=1,q=1,m={m};{chunk}\033\\")
            first = False
        else:
            sys.stdout.write(f"\033_Gq=1,m={m};{chunk}\033\\")
        sys.stdout.flush()
    if cols:
        sys.stdout.write(f"\033_Ga=p,i=1,q=1,c={cols};\033\\")
        sys.stdout.flush()


def _draw_badge(draw, x, y, text, size=28) -> None:
    r = size // 2
    draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 200, 50, 230))
    draw.text((x, y - r * 0.35), str(text), fill=(0, 0, 0, 255), font_size=size - 4, anchor="mt")


def composite_side_by_side(paths: list[Path], max_height: int = 500):
    from PIL import Image, ImageDraw

    images = []
    for p in paths:
        try:
            img = Image.open(p).convert("RGBA")
            if img.size[1] > max_height:
                ratio = max_height / img.size[1]
                img = img.resize(
                    (int(img.size[0] * ratio), max_height), Image.Resampling.LANCZOS
                )
            images.append(img)
        except Exception as e:
            print(f"  Error loading {p}: {e}", file=sys.stderr)
            return None

    if len(images) < 2:
        return None

    gap = 10
    total_w = sum(img.size[0] for img in images) + gap * (len(images) - 1)
    max_h = max(img.size[1] for img in images)
    canvas = Image.new("RGBA", (total_w, max_h), (30, 30, 30, 255))
    draw = ImageDraw.Draw(canvas)
    x = 0
    for i, img in enumerate(images, 1):
        y = (max_h - img.size[1]) // 2
        canvas.paste(img, (x, y), img)
        badge_size = max(20, min(img.size[0], img.size[1]) // 8)
        _draw_badge(draw, x + img.size[0] - badge_size, y + badge_size, i, badge_size)
        x += img.size[0] + gap
    return canvas


def run_undup(
    directory: Path | None = None,
    *,
    ops: OpsConfig | None = None,
    threshold: int | None = None,
    hash_size: int | None = None,
    delete: bool = False,
    confident: bool = False,
    no_kitty: bool = False,
) -> int:
    """Scan directory for near-duplicates (wall-undup). Returns process exit code."""
    ops = ops or OpsConfig()
    root = Path(directory).expanduser() if directory else ops.path("wallpaper_dir")
    root = root.resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    thr = ops.perceptual_hash_threshold if threshold is None else threshold
    hsz = getattr(ops, "hash_size", 8) if hash_size is None else hash_size
    slack = getattr(ops, "hash_consensus_slack", 4)
    if confident:
        delete = True

    kitty = supports_kitty_graphics() and not no_kitty

    print(f"Scanning {root} …", file=sys.stderr)
    groups, _ = find_duplicate_groups(
        root,
        hash_size=hsz,
        threshold=thr,
        consensus_slack=slack,
        progress=True,
    )

    if not groups:
        print("No duplicates found.")
        if thr == 0:
            print(
                f"Try a higher --threshold (default for fetch is {ops.perceptual_hash_threshold})."
            )
        return 0

    print(f"\nFound {len(groups)} duplicate group(s):\n")

    for idx, group in enumerate(groups, 1):
        paths = [Path(p) for p in group["paths"]]
        # Confidence relative to soft threshold (thr + slack) so dual-match
        # near-dups don't always show 0%.
        conf_scale = thr + getattr(ops, "hash_consensus_slack", 4) if thr > 0 else 1
        conf = confidence_score(group["max_dist"], conf_scale)

        fp = group["fingerprint"]
        print(
            f"[{idx}/{len(groups)}] d={fp.dhash[:12]}…  "
            f"max_dist={group['max_dist']}  confidence={conf:.0f}%"
        )
        for p in paths:
            try:
                sz = p.stat().st_size
            except OSError:
                sz = 0
            print(f"    {p}  ({sz / 1024:.0f} KiB)")

        if kitty:
            composite = composite_side_by_side(paths)
            if composite:
                cols = shutil.get_terminal_size().columns - 2
                buf = io.BytesIO()
                composite.save(buf, format="PNG")
                kitty_display(buf.getvalue(), cols=cols)
                if delete:
                    sys.stdout.write("\n")
                    sys.stdout.flush()

        if delete:
            if confident:
                # --confident: only auto-delete high-confidence groups; never
                # fall through to interactive prompts for weak matches.
                if conf >= CONFIDENT_DELETE_MIN:
                    print(
                        f"  High confidence ({conf:.0f}%); "
                        "deleting extras (keeping first)."
                    )
                    for p in paths[1:]:
                        try:
                            p.unlink()
                            print(f"  Deleted {p}")
                        except OSError as e:
                            print(f"  Failed to delete {p}: {e}", file=sys.stderr)
                else:
                    print(
                        f"  Confidence {conf:.0f}% < {CONFIDENT_DELETE_MIN:.0f}%; "
                        "skipping (use --delete without --confident to review)."
                    )
            else:
                print("  Keep which file(s)?")
                print("    [a] Keep all")
                print("    [1] Keep first only, delete rest")
                for i, p in enumerate(paths, 1):
                    print(f"    [{i}] Keep only this one, delete rest")
                try:
                    choice = input("  Choice: ").strip().lower()
                except EOFError:
                    choice = "a"
                if choice == "a":
                    pass
                elif choice == "1":
                    for p in paths[1:]:
                        p.unlink(missing_ok=True)
                        print(f"  Deleted {p}")
                else:
                    try:
                        keep_idx = int(choice) - 1
                        for i, p in enumerate(paths):
                            if i != keep_idx:
                                p.unlink(missing_ok=True)
                                print(f"  Deleted {p}")
                    except (ValueError, IndexError):
                        print("  Invalid choice, skipped.")
        print()

    return 0
