"""Terminal image backends: Kitty graphics → sixel → chafa → Unicode blocks."""

from __future__ import annotations

import base64
import io
import logging
import os
import select
import shutil
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger("wallpaperctl")

# Quiet Kitty id for TUI previews (undup uses 42).
KITTY_TUI_IMAGE_ID = 77


class GraphicsBackend(str, Enum):
    KITTY = "kitty"
    SIXEL = "sixel"
    CHAFA = "chafa"
    BLOCKS = "blocks"
    NONE = "none"


@dataclass(frozen=True)
class GraphicsInfo:
    backend: GraphicsBackend
    detail: str = ""


def have_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def supports_kitty_graphics(*, force: bool | None = None) -> bool:
    """Probe Kitty graphics protocol (cached). *force* overrides for tests."""
    if force is not None:
        return force
    cache = getattr(supports_kitty_graphics, "_cached", None)
    if cache is not None:
        return bool(cache)
    result = _detect_kitty_graphics()
    supports_kitty_graphics._cached = result  # type: ignore[attr-defined]
    return result


def _detect_kitty_graphics() -> bool:
    # Fast path: known terminals that support the protocol
    term = os.environ.get("TERM", "")
    term_prog = os.environ.get("TERM_PROGRAM", "")
    if term_prog == "kitty" or term.startswith("xterm-kitty"):
        return True
    if os.environ.get("KITTY_WINDOW_ID"):
        return True
    # Ghostty / WezTerm / Konsole also speak the protocol
    if term_prog in ("WezTerm", "ghostty") or "ghostty" in term:
        # Still probe if we have a TTY; some builds lack graphics
        pass
    if not sys.stdin.isatty() or not sys.stdout.isatty():
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
            deadline = time.monotonic() + 0.25
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


def supports_sixel(*, force: bool | None = None) -> bool:
    if force is not None:
        return force
    cache = getattr(supports_sixel, "_cached", None)
    if cache is not None:
        return bool(cache)
    result = _detect_sixel()
    supports_sixel._cached = result  # type: ignore[attr-defined]
    return result


def _detect_sixel() -> bool:
    if os.environ.get("TERM", "").endswith("-sixel"):
        return True
    # Tools that can emit sixel even when DA probe fails
    if have_cmd("chafa") or have_cmd("img2sixel"):
        # Only claim sixel if the terminal looks capable
        term = os.environ.get("TERM", "").lower()
        term_prog = os.environ.get("TERM_PROGRAM", "").lower()
        if any(
            x in term or x in term_prog
            for x in ("xterm", "mlterm", "foot", "wezterm", "konsole", "contour")
        ):
            return True
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    # Device attributes: sixel is often bit 4 in primary DA
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
            sys.stdout.buffer.write(b"\033[c")
            sys.stdout.buffer.flush()
            resp = b""
            deadline = time.monotonic() + 0.2
            while time.monotonic() < deadline:
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    chunk = os.read(fd, 1024)
                    if chunk:
                        resp += chunk
                    else:
                        break
            # e.g. \033[?64;1;2;4;6;9;15;18;21;22c  — "4" is sixel
            text = resp.decode("ascii", errors="ignore")
            if ";4;" in text or text.endswith(";4c") or ";4c" in text:
                return True
            return "4" in text and "sixel" in os.environ.get("TERM", "").lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return False


def detect_backend(
    *,
    prefer: str | None = None,
    no_kitty: bool = False,
) -> GraphicsInfo:
    """Pick best available preview backend."""
    if prefer:
        p = prefer.lower().strip()
        if p in ("auto", ""):
            pass
        else:
            try:
                return GraphicsInfo(GraphicsBackend(p), "forced")
            except ValueError:
                log.warning("Unknown graphics backend %r; using auto", prefer)

    if not no_kitty and supports_kitty_graphics():
        return GraphicsInfo(GraphicsBackend.KITTY, "protocol probe / env")
    if supports_sixel() and (have_cmd("chafa") or have_cmd("img2sixel")):
        tool = "chafa" if have_cmd("chafa") else "img2sixel"
        return GraphicsInfo(GraphicsBackend.SIXEL, tool)
    if have_cmd("chafa"):
        return GraphicsInfo(GraphicsBackend.CHAFA, "symbols")
    return GraphicsInfo(GraphicsBackend.BLOCKS, "pillow halfblocks")


def load_png_bytes(path: Path, *, max_w: int = 800, max_h: int = 500) -> bytes | None:
    """Load image, thumbnail, encode PNG for graphics protocols."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True, compress_level=6)
            return buf.getvalue()
    except Exception as e:
        log.debug("load_png_bytes failed for %s: %s", path, e)
        return None


def is_protocol_backend(backend: GraphicsBackend) -> bool:
    """True if the backend paints outside the Textual cell buffer."""
    return backend in (GraphicsBackend.KITTY, GraphicsBackend.SIXEL)


def cursor_seq(row: int, col: int) -> str:
    """1-based cursor position escape sequence."""
    return f"\033[{max(1, int(row))};{max(1, int(col))}H"


def kitty_delete_seq(image_id: int = KITTY_TUI_IMAGE_ID) -> str:
    """Delete a previously placed Kitty image (sequence only)."""
    return f"\033_Ga=d,d=i,i={image_id},q=2\033\\"


def kitty_place_png_seq(
    png: bytes,
    *,
    cols: int = 0,
    rows: int = 0,
    image_id: int = KITTY_TUI_IMAGE_ID,
    z_index: int = -1,
) -> str:
    """Transmit + place PNG at cursor (Kitty a=T). Returns escape string."""
    encoded = base64.b64encode(png).decode("ascii")
    parts: list[str] = []
    first = True
    while encoded:
        chunk, encoded = encoded[:4096], encoded[4096:]
        m = 1 if encoded else 0
        if first:
            ctrl = f"a=T,f=100,i={image_id},q=2,m={m},z={z_index}"
            if cols > 0:
                ctrl += f",c={int(cols)}"
            if rows > 0:
                ctrl += f",r={int(rows)}"
            parts.append(f"\033_G{ctrl};{chunk}\033\\")
            first = False
        else:
            parts.append(f"\033_Gq=2,i={image_id},m={m};{chunk}\033\\")
    return "".join(parts)


def kitty_put_seq(
    *,
    cols: int = 0,
    rows: int = 0,
    image_id: int = KITTY_TUI_IMAGE_ID,
    z_index: int = -1,
) -> str:
    """Re-place an already-transmitted Kitty image at the cursor (a=p)."""
    ctrl = f"a=p,i={image_id},q=2,z={z_index}"
    if cols > 0:
        ctrl += f",c={int(cols)}"
    if rows > 0:
        ctrl += f",r={int(rows)}"
    return f"\033_G{ctrl}\033\\"


def kitty_place_png(
    png: bytes,
    *,
    cols: int = 0,
    rows: int = 0,
    image_id: int = KITTY_TUI_IMAGE_ID,
    z_index: int = -1,
) -> None:
    """Transmit + place PNG at cursor (Kitty protocol, quiet) via stdout."""
    sys.stdout.write(
        kitty_place_png_seq(
            png, cols=cols, rows=rows, image_id=image_id, z_index=z_index
        )
    )
    sys.stdout.flush()


def kitty_delete(image_id: int = KITTY_TUI_IMAGE_ID) -> None:
    """Delete a previously placed Kitty image."""
    try:
        sys.stdout.write(kitty_delete_seq(image_id))
        sys.stdout.flush()
    except Exception:
        pass


def move_cursor(row: int, col: int) -> None:
    """1-based cursor position."""
    sys.stdout.write(cursor_seq(row, col))
    sys.stdout.flush()


def render_sixel(path: Path, *, cols: int = 40, rows: int = 20) -> str | None:
    """Return sixel sequence string for *path*, or None on failure."""
    from wallpaperctl.util import run

    if have_cmd("chafa"):
        r = run(
            [
                "chafa",
                f"--size={cols}x{rows}",
                "--format=sixels",
                "--animate=off",
                str(path),
            ],
            timeout=15,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    if have_cmd("img2sixel"):
        r = run(["img2sixel", "-w", str(max(80, cols * 10)), str(path)], timeout=15)
        if r.returncode == 0 and r.stdout:
            return r.stdout
    return None


def render_chafa_ansi(path: Path, *, cols: int = 40, rows: int = 20) -> str | None:
    """Symbol/ANSI art via chafa (safe inside Textual widgets)."""
    from wallpaperctl.util import run

    if not have_cmd("chafa"):
        return None
    r = run(
        [
            "chafa",
            f"--size={cols}x{rows}",
            "--format=symbols",
            "--animate=off",
            "--colors=256",
            str(path),
        ],
        timeout=15,
    )
    if r.returncode == 0 and r.stdout:
        return r.stdout.rstrip("\n")
    return None


def render_halfblocks(path: Path, *, cols: int = 40, rows: int = 20) -> str:
    """Unicode half-block (▀) preview via Pillow (always available)."""
    try:
        from PIL import Image
    except ImportError:
        return f"(cannot preview: {path.name})"

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            # Each terminal row is two image rows (upper/lower halfblock)
            target_w = max(8, cols)
            target_h = max(4, rows * 2)
            img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
            # Pad height to even
            w, h = img.size
            if h % 2:
                from PIL import Image as Im

                pad = Im.new("RGB", (w, h + 1), (0, 0, 0))
                pad.paste(img, (0, 0))
                img = pad
                h += 1
            px = img.load()
            lines: list[str] = []
            for y in range(0, h, 2):
                parts: list[str] = []
                for x in range(w):
                    r1, g1, b1 = px[x, y]
                    r2, g2, b2 = px[x, y + 1]
                    # Truecolor: fg = upper, bg = lower, char ▀
                    parts.append(
                        f"\033[38;2;{r1};{g1};{b1}m"
                        f"\033[48;2;{r2};{g2};{b2}m▀"
                    )
                parts.append("\033[0m")
                lines.append("".join(parts))
            return "\n".join(lines)
    except Exception as e:
        return f"(preview error: {e})"


def render_ansi_preview(
    path: Path,
    *,
    cols: int = 40,
    rows: int = 20,
    backend: GraphicsBackend | None = None,
) -> tuple[GraphicsBackend, str]:
    """Render a widget-safe ANSI (or message) preview.

    Kitty/sixel placement is handled separately by the TUI; this always returns
    text suitable for a Static/Rich widget (chafa or halfblocks). For kitty/sixel
    backends a short placeholder is returned while the protocol paints over it.
    """
    info = detect_backend() if backend is None else GraphicsInfo(backend)
    b = info.backend

    if b in (GraphicsBackend.CHAFA, GraphicsBackend.KITTY, GraphicsBackend.SIXEL):
        # Prefer chafa symbols for in-widget content even under kitty/sixel
        # (protocol paint is optional overlay). Fall through to blocks.
        ansi = render_chafa_ansi(path, cols=cols, rows=rows)
        if ansi:
            return GraphicsBackend.CHAFA if b == GraphicsBackend.CHAFA else b, ansi

    blocks = render_halfblocks(path, cols=cols, rows=rows)
    return GraphicsBackend.BLOCKS, blocks
