"""migrate --check is read-only and exits 0."""

from __future__ import annotations

from wallpaperctl.config import OpsConfig
from wallpaperctl.maint.migrate import run_migrate_check


def test_migrate_check_returns_zero(capsys) -> None:
    code = run_migrate_check(OpsConfig())
    assert code == 0
    out = capsys.readouterr().out
    assert "PATH resolution" in out
    assert "Suggested cutover" in out
