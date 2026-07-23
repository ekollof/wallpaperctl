"""Tests for undup --confident / --delete behaviour and kitty previews."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image

from wallpaperctl.sources.dedup import Fingerprint, confidence_score
from wallpaperctl.sources.undup import (
    CONFIDENT_DELETE_MIN,
    composite_side_by_side,
    composite_to_png_bytes,
    kitty_display,
    run_undup,
)


def _jpg(path: Path, color: tuple[int, int, int] = (40, 80, 120), size=(64, 48)) -> Path:
    Image.new("RGB", size, color).save(path, quality=90)
    return path


def test_confidence_score_scale():
    assert confidence_score(0, 18) == 100.0
    assert confidence_score(18, 18) == 0.0
    # ~22% at max_dist 14 with soft scale 18
    conf = confidence_score(14, 18)
    assert 20.0 <= conf <= 25.0
    assert conf < CONFIDENT_DELETE_MIN


def test_confident_deletes_only_high_confidence(tmp_path: Path, monkeypatch, capsys):
    """--confident auto-deletes high-confidence groups and skips weak ones."""
    keep_hi = _jpg(tmp_path / "keep_hi.jpg", (10, 20, 30))
    drop_hi = _jpg(tmp_path / "drop_hi.jpg", (10, 20, 30))
    keep_lo = _jpg(tmp_path / "keep_lo.jpg", (200, 10, 10))
    drop_lo = _jpg(tmp_path / "drop_lo.jpg", (10, 200, 10))

    hi_fp = Fingerprint("aaaaaaaaaaaa0000", "bbbbbbbbbbbb0000", "cccccccccccc0000")
    lo_fp = Fingerprint("dddddddddddd0000", "eeeeeeeeeeee0000", "ffffffffffff0000")
    groups = [
        {
            "paths": [str(keep_hi), str(drop_hi)],
            "max_dist": 0,
            "fingerprint": hi_fp,
        },
        {
            "paths": [str(keep_lo), str(drop_lo)],
            "max_dist": 14,  # ~22% confidence with thr+slack=18
            "fingerprint": lo_fp,
        },
    ]

    monkeypatch.setattr(
        "wallpaperctl.sources.undup.find_duplicate_groups",
        lambda *a, **k: (groups, 4),
    )
    monkeypatch.setattr(
        "wallpaperctl.sources.undup.supports_kitty_graphics",
        lambda: False,
    )
    # Must not block on interactive input for low-confidence groups
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=AssertionError("prompt")))

    rc = run_undup(tmp_path, delete=True, confident=True, no_kitty=True, threshold=14)
    assert rc == 0

    assert keep_hi.is_file()
    assert not drop_hi.is_file(), "high-confidence duplicate should be deleted"
    assert keep_lo.is_file()
    assert drop_lo.is_file(), "low-confidence pair must not be auto-deleted"

    out = capsys.readouterr().out
    assert "High confidence" in out
    assert "skipping" in out


def test_confident_alone_implies_delete_high_only(tmp_path: Path, monkeypatch):
    """--confident implies delete, but only for conf >= CONFIDENT_DELETE_MIN."""
    a = _jpg(tmp_path / "a.jpg")
    b = _jpg(tmp_path / "b.jpg")
    groups = [
        {
            "paths": [str(a), str(b)],
            "max_dist": 14,
            "fingerprint": Fingerprint(
                "1111111111110000", "2222222222220000", "3333333333330000"
            ),
        }
    ]
    monkeypatch.setattr(
        "wallpaperctl.sources.undup.find_duplicate_groups",
        lambda *a, **k: (groups, 2),
    )
    monkeypatch.setattr(
        "wallpaperctl.sources.undup.supports_kitty_graphics",
        lambda: False,
    )
    prompt = MagicMock(side_effect=AssertionError("must not prompt"))
    monkeypatch.setattr("builtins.input", prompt)

    rc = run_undup(tmp_path, confident=True, no_kitty=True, threshold=14)
    assert rc == 0
    assert a.is_file() and b.is_file()
    prompt.assert_not_called()


def test_composite_scales_large_wallpapers(tmp_path: Path):
    """Side-by-side previews must stay under kitty-friendly dimensions."""
    a = _jpg(tmp_path / "a.jpg", (10, 20, 30), size=(3840, 2160))
    b = _jpg(tmp_path / "b.jpg", (200, 100, 50), size=(3840, 2160))
    composite = composite_side_by_side([a, b], max_width=1400, max_height=420)
    assert composite is not None
    w, h = composite.size
    assert w <= 1400
    assert h <= 420
    png = composite_to_png_bytes(composite)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # Compact enough that kitty should not ENOMEM on typical quotas.
    assert len(png) < 1_500_000


def test_kitty_display_uses_quiet_mode(monkeypatch):
    """q=2 must be used so ENOMEM replies never leak as TTY garbage."""
    writes: list[str] = []

    class _Stdout:
        def write(self, s: str) -> int:
            writes.append(s)
            return len(s)

        def flush(self) -> None:
            pass

    monkeypatch.setattr("wallpaperctl.sources.undup.sys.stdout", _Stdout())
    monkeypatch.setattr("wallpaperctl.sources.undup._drain_stdin", lambda *a, **k: None)

    # Tiny fake PNG payload
    kitty_display(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, cols=80)
    joined = "".join(writes)
    assert "q=2" in joined
    assert "q=1" not in joined
    assert "a=T" in joined
