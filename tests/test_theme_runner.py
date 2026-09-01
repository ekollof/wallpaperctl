"""Theme runner timeout and retry wiring."""

from __future__ import annotations

from pathlib import Path
from time import sleep as real_sleep
from unittest.mock import patch

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.theme import runner as theme_runner


class _FakeOp:
    def __init__(
        self,
        name: str,
        *,
        results: list[bool] | None = None,
        delay: float = 0.0,
        enabled: bool = True,
    ) -> None:
        self.name = name
        self.enabled_flag = enabled
        self.results = list(results if results is not None else [True])
        self.delay = delay
        self.calls = 0

    def enabled(self, ctx: WallpaperContext) -> bool:
        return self.enabled_flag

    def run(self, ctx: WallpaperContext) -> bool:
        self.calls += 1
        if self.delay:
            # Use unbound real sleep so tests can patch theme_runner.time.sleep
            # without making the op finish instantly.
            real_sleep(self.delay)
        if not self.results:
            return True
        return self.results.pop(0)


def _ctx(tmp_path: Path, **ops_kw) -> WallpaperContext:
    ops = OpsConfig()
    for k, v in ops_kw.items():
        setattr(ops, k, v)
    img = tmp_path / "w.jpg"
    img.write_bytes(b"x")
    return WallpaperContext(
        path=img,
        de=DesktopEnvironment(),
        ops=ops,
    )


def test_runner_retries_failed_ops(tmp_path: Path) -> None:
    op = _FakeOp("wallust", results=[False, True])
    ctx = _ctx(tmp_path, max_retries=3, retry_delay=0.01, wallust_timeout=5)
    with (
        patch.object(theme_runner, "THEME_OPS", [op]),
        patch.object(theme_runner.time, "sleep", lambda s: None),
    ):
        failed, total = theme_runner.run_theme_ops(ctx)
    assert total == 1
    assert failed == 0
    assert op.calls == 2


def test_runner_counts_failure_after_retries(tmp_path: Path) -> None:
    op = _FakeOp("openrgb", results=[False, False, False])
    ctx = _ctx(tmp_path, max_retries=3, retry_delay=0.0, openrgb_timeout=5)
    with (
        patch.object(theme_runner, "THEME_OPS", [op]),
        patch.object(theme_runner.time, "sleep", lambda s: None),
    ):
        failed, total = theme_runner.run_theme_ops(ctx)
    assert total == 1
    assert failed == 1
    assert op.calls == 3


def test_runner_times_out_slow_op(tmp_path: Path) -> None:
    op = _FakeOp("gtk-theme", results=[True], delay=2.0)
    ctx = _ctx(tmp_path, max_retries=1, operation_timeout=0.2)
    with (
        patch.object(theme_runner, "THEME_OPS", [op]),
        patch.object(theme_runner.time, "sleep", lambda s: None),
    ):
        failed, total = theme_runner.run_theme_ops(ctx)
    assert total == 1
    assert failed == 1


def test_enable_starttree_removed() -> None:
    assert not hasattr(OpsConfig(), "enable_starttree")


def test_omarchy_timeout_uses_ops_budget(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, omarchy_timeout=90, operation_timeout=30)
    assert theme_runner._timeout_for("omarchy", ctx) == 95.0
    assert theme_runner._timeout_for("gtk-theme", ctx) == 30.0


def test_omarchy_op_is_not_retried(tmp_path: Path) -> None:
    op = _FakeOp("omarchy", results=[False, True])
    ctx = _ctx(tmp_path, max_retries=3, retry_delay=0.0, omarchy_timeout=5)
    with (
        patch.object(theme_runner, "THEME_OPS", [op]),
        patch.object(theme_runner.time, "sleep", lambda s: None),
    ):
        failed, total = theme_runner.run_theme_ops(ctx)
    assert total == 1
    assert failed == 1
    assert op.calls == 1
