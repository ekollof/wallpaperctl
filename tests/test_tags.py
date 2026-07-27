"""Tag store persistence."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.tui.tags import TagStore


def test_tag_store_add_remove_roundtrip(tmp_path: Path) -> None:
    store = TagStore(tmp_path / "tags.json")
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")

    assert store.get(img) == []
    store.add(img, "nature", "dark")
    assert store.get(img) == ["dark", "nature"]

    store2 = TagStore(tmp_path / "tags.json")
    assert store2.get(img) == ["dark", "nature"]
    assert "nature" in store2.all_tags()

    store2.remove(img, "dark")
    assert store2.get(img) == ["nature"]
    store2.remove(img, "nature")
    assert store2.get(img) == []
    assert img.resolve().as_posix() not in {
        Path(k).as_posix() for k in store2._data
    } or store2.get(img) == []


def test_tag_store_drop_path(tmp_path: Path) -> None:
    store = TagStore(tmp_path / "tags.json")
    img = tmp_path / "b.png"
    img.write_bytes(b"x")
    store.add(img, "x")
    store.drop_path(img)
    assert store.get(img) == []
