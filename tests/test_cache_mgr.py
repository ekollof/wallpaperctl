from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.sources import cache_mgr


def _ops(tmp: Path) -> OpsConfig:
    ops = OpsConfig()
    ops.url_log = str(tmp / "urls")
    ops.hash_cache = str(tmp / "hashes")
    return ops


def test_trim_and_clear(tmp_path: Path):
    ops = _ops(tmp_path)
    url = Path(ops.url_log)
    url.write_text("\n".join(f"url{i}" for i in range(25)) + "\n", encoding="utf-8")
    hash_p = Path(ops.hash_cache)
    hash_p.write_text("# header\na b c /tmp/x\n", encoding="utf-8")

    stats = cache_mgr.cache_stats(ops)
    assert stats.url_entries == 25
    assert stats.hash_entries == 1

    n = cache_mgr.trim_url_cache(10, ops)
    assert n == 10
    assert url.read_text(encoding="utf-8").strip().splitlines()[-1] == "url24"

    cleared = cache_mgr.clear_all_caches(ops)
    assert "URL log" in cleared
    assert "hash index" in cleared
    assert not url.exists()
    assert not hash_p.exists()


def test_status_no_files(tmp_path: Path, capsys):
    ops = _ops(tmp_path)
    cache_mgr.show_cache(ops)
    out = capsys.readouterr().out
    assert "not found" in out.lower() or "URL log" in out
