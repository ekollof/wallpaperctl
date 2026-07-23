from wallpaperctl.config import OpsConfig, _parse_sh_exports
from pathlib import Path
import tempfile


def test_parse_sh_exports():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "config.sh"
        p.write_text(
            'export UNSPLASH_ACCESS_KEY="abc"\n'
            "PEXELS_API_KEY=def\n"
            "# comment\n"
            "CATEGORIES=nature,space\n",
            encoding="utf-8",
        )
        vals = _parse_sh_exports(p)
        assert vals["UNSPLASH_ACCESS_KEY"] == "abc"
        assert vals["PEXELS_API_KEY"] == "def"
        assert vals["CATEGORIES"] == "nature,space"


def test_ops_env_overrides_plasma():
    ops = OpsConfig()
    ops.apply_env_overrides(
        is_plasma=True, is_hyprland=False, is_xfce=False, is_cinnamon=False
    )
    assert ops.enable_xresources is False
    assert ops.enable_notifications is False
