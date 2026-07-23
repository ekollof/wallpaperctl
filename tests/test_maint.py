from pathlib import Path
import time

from wallpaperctl.maint.cleanup import run_cleanup
from wallpaperctl.maint.verify import run_verify
from wallpaperctl.config import OpsConfig


def test_cleanup_prunes_old_backups(tmp_path: Path, monkeypatch):
    themes = tmp_path / ".themes"
    themes.mkdir()
    # three backups with increasing mtimes
    for i, name in enumerate(
        [
            "cinnamon-dynamic.backup.20200101_000000",
            "cinnamon-dynamic.backup.20200201_000000",
            "cinnamon-dynamic.backup.20200301_000000",
        ]
    ):
        d = themes / name
        d.mkdir()
        (d / "marker").write_text("x", encoding="utf-8")
        # stagger mtimes
        t = time.time() - (3 - i) * 1000
        Path(d).touch()
        import os

        os.utime(d, (t, t))

    dyn = themes / "cinnamon-dynamic"
    dyn.mkdir()
    (dyn / "foo.tmp").write_text("tmp", encoding="utf-8")

    monkeypatch.setattr(
        "wallpaperctl.maint.cleanup.home",
        lambda: tmp_path,
    )
    assert run_cleanup(keep_backups=2) == 0
    remaining = list(themes.glob("cinnamon-dynamic.backup.*"))
    assert len(remaining) == 2
    assert not (dyn / "foo.tmp").exists()


def test_verify_wal_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("wallpaperctl.maint.verify.home", lambda: tmp_path)
    # no colors file
    rc = run_verify("wal", ops=OpsConfig())
    assert rc == 1
