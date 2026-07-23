"""URL + multi-algorithm perceptual duplicate detection.

Improvements over the old single dHash/threshold=10 path:
  * dHash + pHash + aHash fingerprints (credit bars / crops / re-encodes)
  * Compares against the full ~/Wallpapers library, not only a thin URL cache
  * Tunable thresholds with consensus voting so near-dups are caught more reliably
  * Cache format v2 (backward-compatible with old single-hex lines)
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.util import log_error

log = logging.getLogger("wallpaperctl")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}

# Cache header so we can evolve the format
CACHE_HEADER = "# wallpaperctl-hash-cache-v2 dhash phash ahash [path]"


@dataclass(frozen=True)
class Fingerprint:
    """Perceptual fingerprint (hex strings from imagehash)."""

    dhash: str
    phash: str
    ahash: str
    path: str = ""

    def line(self) -> str:
        base = f"{self.dhash} {self.phash} {self.ahash}"
        if self.path:
            return f"{base} {self.path}"
        return base


@dataclass
class MatchResult:
    matched: bool
    reason: str = ""
    distance: int | None = None
    against: Fingerprint | None = None


def _lazy_imagehash():
    import imagehash
    from PIL import Image

    return imagehash, Image


def extract_unsplash_id(url: str) -> str:
    m = re.search(r"(photo-[0-9a-zA-Z-]+)", url)
    return m.group(1) if m else url


def check_value_for_url(image_url: str, provider: str) -> str:
    if provider == "Unsplash":
        return extract_unsplash_id(image_url)
    return image_url


def is_url_duplicate(image_url: str, provider: str, url_log: Path) -> bool:
    value = check_value_for_url(image_url, provider)
    if not url_log.is_file():
        return False
    try:
        for line in url_log.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip() == value:
                log.debug("Duplicate URL/ID: %s from %s", value, provider)
                return True
    except OSError:
        pass
    return False


def log_url(image_url: str, provider: str, url_log: Path) -> None:
    value = check_value_for_url(image_url, provider)
    try:
        with url_log.open("a", encoding="utf-8") as f:
            f.write(value + "\n")
    except OSError as e:
        log.warning("Failed to log URL to %s: %s", url_log, e)


def compute_fingerprint(path: Path, *, hash_size: int = 8) -> Fingerprint | None:
    """Compute multi-algorithm fingerprint for an image."""
    try:
        imagehash, Image = _lazy_imagehash()
        with Image.open(path) as img:
            img = img.convert("RGB")
            # Slight blur/normalize resilience: use full image; credit bar is
            # a small SE strip that multi-hash consensus handles better than
            # a single dHash.
            d = imagehash.dhash(img, hash_size=hash_size)
            p = imagehash.phash(img, hash_size=hash_size)
            a = imagehash.average_hash(img, hash_size=hash_size)
            return Fingerprint(dhash=str(d), phash=str(p), ahash=str(a), path=str(path))
    except Exception as e:
        log.debug("Failed to fingerprint %s: %s", path, e)
        return None


# Back-compat name used by older call sites / tests
def compute_dhash(path: Path) -> str | None:
    fp = compute_fingerprint(path)
    return fp.dhash if fp else None


def _hamming(imagehash, hex_a: str, hex_b: str) -> int | None:
    try:
        return int(imagehash.hex_to_hash(hex_a) - imagehash.hex_to_hash(hex_b))
    except Exception:
        return None


def compare_fingerprints(
    a: Fingerprint,
    b: Fingerprint,
    *,
    threshold: int,
    consensus_slack: int = 4,
) -> MatchResult:
    """
    Decide if two fingerprints are near-duplicates.

    Match when:
      1. dHash OR pHash distance <= threshold (strong single-algorithm hit), or
      2. *Both* dHash and pHash are within threshold+slack (dual soft match).
         aHash alone is not enough — it's too coarse for landscape photos and
         caused single-link clustering false positives in undup.
    """
    imagehash, _ = _lazy_imagehash()
    d_d = _hamming(imagehash, a.dhash, b.dhash)
    d_p = _hamming(imagehash, a.phash, b.phash)
    if d_d is None and d_p is None:
        return MatchResult(False)

    if d_d is not None and d_d <= threshold:
        return MatchResult(True, reason=f"dhash≤{threshold}", distance=d_d, against=b)
    if d_p is not None and d_p <= threshold:
        return MatchResult(True, reason=f"phash≤{threshold}", distance=d_p, against=b)

    # Dual soft: both structure hashes agree that images are near — handles
    # credit bars / mild re-encodes without aHash false friends.
    soft = threshold + max(0, consensus_slack)
    if (
        d_d is not None
        and d_p is not None
        and d_d <= soft
        and d_p <= soft
    ):
        best = min(d_d, d_p)
        return MatchResult(
            True,
            reason=f"dual[dhash+phash]≤{soft}",
            distance=best,
            against=b,
        )
    return MatchResult(False)


def parse_cache_line(line: str) -> Fingerprint | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split()
    if len(parts) == 1:
        # Legacy single dHash line
        h = parts[0]
        return Fingerprint(dhash=h, phash=h, ahash=h)
    if len(parts) >= 3:
        # Path may contain spaces — take remainder after the three hashes
        path = " ".join(parts[3:]) if len(parts) >= 4 else ""
        return Fingerprint(dhash=parts[0], phash=parts[1], ahash=parts[2], path=path)
    return None


def load_fingerprint_cache(cache: Path) -> list[Fingerprint]:
    if not cache.is_file():
        return []
    out: list[Fingerprint] = []
    try:
        for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
            fp = parse_cache_line(line)
            if fp:
                out.append(fp)
    except OSError as e:
        log.debug("Failed reading hash cache: %s", e)
    return out


def log_fingerprint(fp: Fingerprint, cache: Path) -> None:
    try:
        new_file = not cache.is_file() or cache.stat().st_size == 0
        with cache.open("a", encoding="utf-8") as f:
            if new_file:
                f.write(CACHE_HEADER + "\n")
            f.write(fp.line() + "\n")
    except OSError as e:
        log.warning("Failed to log hash to %s: %s", cache, e)


# Back-compat
def log_hash(hash_hex: str, cache: Path) -> None:
    log_fingerprint(Fingerprint(dhash=hash_hex, phash=hash_hex, ahash=hash_hex), cache)


def is_perceptual_duplicate(
    hash_hex: str,
    cache: Path,
    threshold: int,
) -> bool:
    """Legacy API: single dHash hex vs cache."""
    probe = Fingerprint(dhash=hash_hex, phash=hash_hex, ahash=hash_hex)
    for entry in load_fingerprint_cache(cache):
        if compare_fingerprints(probe, entry, threshold=threshold).matched:
            return True
    return False


def find_duplicate(
    path: Path,
    ops: OpsConfig,
    *,
    index: list[Fingerprint] | None = None,
) -> MatchResult:
    """Fingerprint *path* and compare against the in-memory index."""
    hash_size = getattr(ops, "hash_size", 8) or 8
    threshold = ops.perceptual_hash_threshold
    slack = getattr(ops, "hash_consensus_slack", 4)
    fp = compute_fingerprint(path, hash_size=hash_size)
    if fp is None:
        return MatchResult(False, reason="unreadable")

    entries = index if index is not None else load_fingerprint_cache(ops.path("hash_cache"))
    for entry in entries:
        # Skip comparing a file to itself
        if entry.path and Path(entry.path).resolve() == path.resolve():
            continue
        result = compare_fingerprints(
            fp, entry, threshold=threshold, consensus_slack=slack
        )
        if result.matched:
            log.debug(
                "Perceptual duplicate: %s vs %s (%s dist=%s)",
                path.name,
                entry.path or entry.dhash[:12],
                result.reason,
                result.distance,
            )
            return result
    return MatchResult(False)


class LibraryIndex:
    """In-memory fingerprint index of the wallpaper library + on-disk cache."""

    def __init__(self, ops: OpsConfig) -> None:
        self.ops = ops
        self.entries: list[Fingerprint] = []
        self._loaded = False

    def ensure_loaded(self, *, progress: bool = True) -> list[Fingerprint]:
        if self._loaded:
            return self.entries
        self.entries = self._build(progress=progress)
        self._loaded = True
        return self.entries

    def _build(self, *, progress: bool) -> list[Fingerprint]:
        cache_path = self.ops.path("hash_cache")
        wall_dir = self.ops.path("wallpaper_dir")
        hash_size = getattr(self.ops, "hash_size", 8) or 8

        cached = load_fingerprint_cache(cache_path)
        # Map resolved path → fingerprint for files we already know
        by_path: dict[str, Fingerprint] = {}
        pathless: list[Fingerprint] = []
        for fp in cached:
            if fp.path:
                try:
                    key = str(Path(fp.path).expanduser().resolve())
                except OSError:
                    key = str(Path(fp.path).expanduser())
                # Prefer entries that already have distinct multi-hashes
                by_path[key] = fp
            else:
                pathless.append(fp)

        files: list[Path] = []
        if wall_dir.is_dir():
            for p in sorted(wall_dir.rglob("*")):
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith("."):
                    files.append(p.resolve())

        entries: list[Fingerprint] = []
        # Keep pathless only if we have no path-keyed library yet (legacy bootstrap)
        if not by_path:
            entries.extend(pathless)

        new_fps: list[Fingerprint] = []
        scanned = 0
        for fpath in files:
            key = str(fpath)
            existing = by_path.get(key)
            # Re-fingerprint legacy rows that stored dhash thrice (pathless clone)
            if (
                existing is not None
                and existing.dhash == existing.phash == existing.ahash
                and len(existing.dhash) <= 16
            ):
                existing = None
            if existing is not None:
                # Normalize stored path to resolved form
                if existing.path != key:
                    existing = Fingerprint(
                        existing.dhash, existing.phash, existing.ahash, path=key
                    )
                entries.append(existing)
                continue
            fp = compute_fingerprint(fpath, hash_size=hash_size)
            scanned += 1
            if progress and scanned % 50 == 0:
                print(f"  Indexing library… {scanned} new files", file=sys.stderr)
            if fp is None:
                continue
            # Always store resolved absolute path
            fp = Fingerprint(fp.dhash, fp.phash, fp.ahash, path=key)
            entries.append(fp)
            new_fps.append(fp)

        # Always rewrite when we learned something or pathless legacy still present
        if new_fps or pathless or any(
            not e.path or " " in e.path for e in entries
        ):
            self._rewrite_cache(cache_path, entries)
            if progress and (new_fps or pathless):
                print(
                    f"  Indexed {len(files)} library images "
                    f"({len(new_fps)} newly fingerprinted, {len(entries)} total fingerprints)",
                    file=sys.stderr,
                )
        else:
            log.debug(
                "Library index ready: %s fingerprints (%s files on disk)",
                len(entries),
                len(files),
            )
        return entries

    def _rewrite_cache(self, cache_path: Path, entries: list[Fingerprint]) -> None:
        # Prefer path-keyed entries; drop pure legacy pathless once library is indexed
        seen_paths: set[str] = set()
        seen_hashes: set[tuple[str, str, str]] = set()
        lines = [CACHE_HEADER]
        for fp in entries:
            if fp.path:
                try:
                    p = str(Path(fp.path).expanduser().resolve())
                except OSError:
                    p = fp.path
                if p in seen_paths:
                    continue
                seen_paths.add(p)
                lines.append(f"{fp.dhash} {fp.phash} {fp.ahash} {p}")
            else:
                key = (fp.dhash, fp.phash, fp.ahash)
                if key in seen_hashes:
                    continue
                seen_hashes.add(key)
                lines.append(f"{fp.dhash} {fp.phash} {fp.ahash}")
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as e:
            log.warning("Failed to write hash cache: %s", e)


    def is_duplicate(self, path: Path) -> MatchResult:
        self.ensure_loaded()
        return find_duplicate(path, self.ops, index=self.entries)

    def add(self, path: Path) -> Fingerprint | None:
        """Fingerprint path, append to index + cache if not already a dup."""
        hash_size = getattr(self.ops, "hash_size", 8) or 8
        fp = compute_fingerprint(path, hash_size=hash_size)
        if fp is None:
            return None
        self.ensure_loaded(progress=False)
        self.entries.append(fp)
        log_fingerprint(fp, self.ops.path("hash_cache"))
        return fp


def clear_caches(ops: OpsConfig | None = None) -> bool:
    """Clear URL + hash caches. Prefer cache_mgr.clear_all_caches for details."""
    from wallpaperctl.sources.cache_mgr import clear_all_caches

    return bool(clear_all_caches(ops))


def check_aspect_ratio(path: Path, ops: OpsConfig) -> bool:
    from wallpaperctl.sources.optimize import image_size

    size = image_size(path)
    if not size:
        log_error(f"Failed to get dimensions for {path}")
        return False
    w, h = size
    if h == 0:
        return False
    aspect = w / h
    log.debug("Image %s dimensions %sx%s, aspect %.3f", path, w, h, aspect)
    return ops.aspect_min <= aspect <= ops.aspect_max


# ---------------------------------------------------------------------------
# Library undup (wall-undup integration)
# ---------------------------------------------------------------------------


def find_duplicate_groups(
    directory: Path,
    *,
    hash_size: int = 8,
    threshold: int = 12,
    consensus_slack: int = 4,
    progress: bool = True,
) -> tuple[list[dict], int]:
    """
    Scan *directory* for near-duplicate groups (wall-undup style).

    Returns (groups, file_count). Each group is:
      {paths: [...], max_dist: int, fingerprint: Fingerprint}
    """
    items: list[tuple[Path, Fingerprint]] = []
    count = 0
    for fpath in sorted(directory.rglob("*")):
        if not fpath.is_file() or fpath.suffix.lower() not in IMAGE_EXTS:
            continue
        if fpath.name.startswith("."):
            continue
        fp = compute_fingerprint(fpath, hash_size=hash_size)
        if fp is None:
            continue
        items.append((fpath, fp))
        count += 1
        if progress and count % 100 == 0:
            print(f"  Scanned {count} files…", file=sys.stderr)

    if progress:
        print(f"  Scanned {count} files total", file=sys.stderr)

    if threshold == 0:
        # Exact multi-hash match
        buckets: dict[tuple[str, str, str], list[Path]] = {}
        for path, fp in items:
            key = (fp.dhash, fp.phash, fp.ahash)
            buckets.setdefault(key, []).append(path)
        groups = [
            {
                "paths": paths,
                "max_dist": 0,
                "fingerprint": Fingerprint(*key),
            }
            for key, paths in buckets.items()
            if len(paths) >= 2
        ]
        return groups, count

    # Complete-link clustering: a candidate must match *every* member of the
    # group (prevents long single-link chains of vaguely similar landscapes).
    groups: list[dict] = []
    for path, fp in items:
        placed = False
        for g in groups:
            member_fps: list[Fingerprint] = g["fps"]
            pair_results = [
                compare_fingerprints(
                    fp, other, threshold=threshold, consensus_slack=consensus_slack
                )
                for other in member_fps
            ]
            if all(r.matched for r in pair_results):
                g["paths"].append(path)
                for r in pair_results:
                    if r.distance is not None and r.distance > g["max_dist"]:
                        g["max_dist"] = r.distance
                g["fps"].append(fp)
                placed = True
                break
        if not placed:
            groups.append(
                {
                    "paths": [path],
                    "max_dist": 0,
                    "fingerprint": fp,
                    "fps": [fp],
                }
            )

    return [g for g in groups if len(g["paths"]) >= 2], count


def confidence_score(max_dist: int, threshold: int) -> float:
    if threshold <= 0:
        return 100.0
    return max(0.0, 100.0 * (1 - max_dist / threshold))
