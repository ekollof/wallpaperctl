from pathlib import Path

from PIL import Image

from wallpaperctl.sources.optimize import add_credits, is_image, optimize_image


def test_optimize_and_credits(tmp_path: Path):
    src = tmp_path / "src.jpg"
    # Wide landscape so aspect passes and fit works
    Image.new("RGB", (2400, 1200), color=(40, 80, 120)).save(src, quality=90)
    assert is_image(src)

    opt = tmp_path / "out_opt.jpg"
    optimize_image(src, opt, width=1920, height=1080)
    assert opt.is_file()
    assert is_image(opt)
    with Image.open(opt) as im:
        assert im.size == (1920, 1080)

    credited = add_credits(opt, "Ada Lovelace", "ada", "Unsplash")
    assert credited.name.endswith("_credited.jpg")
    assert credited.is_file()
    assert is_image(credited)
    # original optimized file removed on success
    assert not opt.exists()
