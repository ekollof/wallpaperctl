"""Persistent per-wallpaper tags (~/.config/wallpaperctl/tags.json)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from wallpaperctl.util import home

log = logging.getLogger("wallpaperctl")

def default_tags_path() -> Path:
    return home() / ".config" / "wallpaperctl" / "tags.json"


class TagStore:
    """Map absolute wallpaper paths → sorted unique tags."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_tags_path()
        self._data: dict[str, list[str]] = {}
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            self._data = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                self._data = {}
                return
            out: dict[str, list[str]] = {}
            for k, v in raw.items():
                if isinstance(v, list):
                    tags = sorted({str(t).strip() for t in v if str(t).strip()})
                    if tags:
                        out[str(k)] = tags
            self._data = out
        except Exception as e:
            log.warning("Failed to load tags from %s: %s", self.path, e)
            self._data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def _key(self, path: Path) -> str:
        return str(path.expanduser().resolve())

    def get(self, path: Path) -> list[str]:
        return list(self._data.get(self._key(path), []))

    def set_tags(self, path: Path, tags: list[str]) -> None:
        key = self._key(path)
        cleaned = sorted({t.strip() for t in tags if t.strip()})
        if cleaned:
            self._data[key] = cleaned
        else:
            self._data.pop(key, None)
        self.save()

    def add(self, path: Path, *tags: str) -> list[str]:
        cur = set(self.get(path))
        for t in tags:
            t = t.strip()
            if t:
                cur.add(t)
        self.set_tags(path, sorted(cur))
        return self.get(path)

    def remove(self, path: Path, *tags: str) -> list[str]:
        cur = set(self.get(path))
        for t in tags:
            cur.discard(t.strip())
        self.set_tags(path, sorted(cur))
        return self.get(path)

    def all_tags(self) -> list[str]:
        s: set[str] = set()
        for tags in self._data.values():
            s.update(tags)
        return sorted(s)

    def paths_with_tag(self, tag: str) -> set[str]:
        tag = tag.strip()
        return {k for k, tags in self._data.items() if tag in tags}

    def drop_path(self, path: Path) -> None:
        self._data.pop(self._key(path), None)
        self.save()
