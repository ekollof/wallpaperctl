"""LRU + optional disk cache for TUI preview payloads (PNG / sixel / ANSI)."""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from wallpaperctl.util import home

log = logging.getLogger("wallpaperctl")

# Memory budget: keep recent previews hot while browsing the library.
_DEFAULT_MAX_ENTRIES = 96
_DISK_DIR = home() / ".cache" / "wallpaperctl" / "previews"


def _file_stamp(path: Path) -> tuple[str, int, int]:
    """(resolved, mtime_ns, size) for cache invalidation."""
    try:
        st = path.stat()
        return str(path.resolve()), int(st.st_mtime_ns), int(st.st_size)
    except OSError:
        return str(path), 0, 0


def _bucket(n: int, step: int = 8) -> int:
    """Quantize dimensions so tiny layout jitter reuses cache entries."""
    n = max(1, int(n))
    return max(step, ((n + step - 1) // step) * step)


@dataclass(frozen=True)
class PngPayload:
    data: bytes
    width: int
    height: int


class PreviewCache:
    """Process-wide preview cache (thread-safe)."""

    def __init__(
        self,
        *,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
        disk: bool = True,
        disk_dir: Path | None = None,
    ) -> None:
        self.max_entries = max_entries
        self.disk = disk
        self.disk_dir = disk_dir or _DISK_DIR
        self._lock = threading.Lock()
        self._lru: OrderedDict[str, object] = OrderedDict()

    def clear(self) -> None:
        with self._lock:
            self._lru.clear()

    def _get(self, key: str) -> object | None:
        with self._lock:
            if key not in self._lru:
                return None
            self._lru.move_to_end(key)
            return self._lru[key]

    def _put(self, key: str, value: object) -> None:
        with self._lock:
            if key in self._lru:
                self._lru.move_to_end(key)
            self._lru[key] = value
            while len(self._lru) > self.max_entries:
                self._lru.popitem(last=False)

    def _disk_path(self, key: str, suffix: str) -> Path:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
        return self.disk_dir / f"{h}{suffix}"

    def get_png(self, path: Path, *, max_w: int, max_h: int) -> PngPayload | None:
        max_w, max_h = _bucket(max_w, 32), _bucket(max_h, 32)
        resolved, mtime_ns, size = _file_stamp(path)
        key = f"png:{resolved}:{mtime_ns}:{size}:{max_w}x{max_h}"
        hit = self._get(key)
        if isinstance(hit, PngPayload):
            return hit

        # Disk: raw PNG + sibling .meta "W H"
        if self.disk:
            dpath = self._disk_path(key, ".png")
            mpath = self._disk_path(key, ".png.meta")
            try:
                if dpath.is_file() and mpath.is_file():
                    meta = mpath.read_text(encoding="utf-8").strip().split()
                    if len(meta) == 2:
                        payload = PngPayload(
                            dpath.read_bytes(), int(meta[0]), int(meta[1])
                        )
                        self._put(key, payload)
                        return payload
            except OSError:
                pass

        from wallpaperctl.term_graphics import load_png_with_size

        loaded = load_png_with_size(path, max_w=max_w, max_h=max_h)
        if loaded is None:
            return None
        data, w, h = loaded
        payload = PngPayload(data, w, h)
        self._put(key, payload)
        if self.disk:
            try:
                self.disk_dir.mkdir(parents=True, exist_ok=True)
                dpath = self._disk_path(key, ".png")
                mpath = self._disk_path(key, ".png.meta")
                tmp = dpath.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(dpath)
                mpath.write_text(f"{w} {h}\n", encoding="utf-8")
            except OSError as e:
                log.debug("preview disk cache write failed: %s", e)
        return payload

    def get_sixel(self, path: Path, *, cols: int, rows: int) -> str | None:
        cols, rows = _bucket(cols, 4), _bucket(rows, 4)
        resolved, mtime_ns, size = _file_stamp(path)
        key = f"sixel:{resolved}:{mtime_ns}:{size}:{cols}x{rows}"
        hit = self._get(key)
        if isinstance(hit, str):
            return hit

        if self.disk:
            dpath = self._disk_path(key, ".six")
            try:
                if dpath.is_file():
                    text = dpath.read_text(encoding="utf-8", errors="replace")
                    if text:
                        self._put(key, text)
                        return text
            except OSError:
                pass

        from wallpaperctl.term_graphics import render_sixel

        text = render_sixel(path, cols=cols, rows=rows)
        if not text:
            return None
        self._put(key, text)
        if self.disk:
            try:
                self.disk_dir.mkdir(parents=True, exist_ok=True)
                dpath = self._disk_path(key, ".six")
                tmp = dpath.with_suffix(".tmp")
                tmp.write_text(text, encoding="utf-8")
                tmp.replace(dpath)
            except OSError as e:
                log.debug("sixel disk cache write failed: %s", e)
        return text

    def get_ansi(self, path: Path, *, cols: int, rows: int) -> str | None:
        cols, rows = _bucket(cols, 4), _bucket(rows, 4)
        resolved, mtime_ns, size = _file_stamp(path)
        key = f"ansi:{resolved}:{mtime_ns}:{size}:{cols}x{rows}"
        hit = self._get(key)
        if isinstance(hit, str):
            return hit

        from wallpaperctl.term_graphics import render_chafa_ansi, render_halfblocks

        text = render_chafa_ansi(path, cols=cols, rows=rows)
        if not text:
            text = render_halfblocks(path, cols=cols, rows=rows)
        if not text:
            return None
        self._put(key, text)
        return text

    def get_image_size(self, path: Path) -> tuple[int, int]:
        resolved, mtime_ns, size = _file_stamp(path)
        key = f"size:{resolved}:{mtime_ns}:{size}"
        hit = self._get(key)
        if isinstance(hit, tuple) and len(hit) == 2:
            return hit  # type: ignore[return-value]

        from wallpaperctl.term_graphics import image_pixel_size

        wh = image_pixel_size(path)
        self._put(key, wh)
        return wh


# Shared singleton for the manage TUI process
_CACHE: PreviewCache | None = None
_CACHE_LOCK = threading.Lock()


def get_preview_cache() -> PreviewCache:
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is None:
            _CACHE = PreviewCache()
        return _CACHE
