from pathlib import Path

from PIL import Image, ImageDraw

from wallpaperctl.config import OpsConfig
from wallpaperctl.sources.dedup import (
    LibraryIndex,
    compare_fingerprints,
    compute_fingerprint,
    find_duplicate_groups,
    parse_cache_line,
)


def _solid(path: Path, color: tuple[int, int, int], size=(640, 360)) -> None:
    Image.new("RGB", size, color).save(path, quality=90)


def _near_copy(src: Path, dest: Path) -> None:
    """Slightly modified copy (credit bar) that should still near-match."""
    with Image.open(src) as im:
        im = im.convert("RGB")
        draw = ImageDraw.Draw(im)
        w, h = im.size
        draw.rectangle([w - 180, h - 30, w - 10, h - 10], fill=(0, 0, 0))
        draw.text((w - 170, h - 28), "Photo by Test", fill=(255, 255, 255))
        im.save(dest, quality=88)


def test_multi_hash_catches_credit_bar(tmp_path: Path):
    a = tmp_path / "a.jpg"
    b = tmp_path / "b_credited.jpg"
    _solid(a, (40, 120, 200))
    # richer image so hashes aren't all-zero
    with Image.open(a) as im:
        draw = ImageDraw.Draw(im)
        draw.ellipse([80, 40, 280, 220], fill=(220, 180, 40))
        draw.rectangle([0, 200, 640, 360], fill=(20, 80, 40))
        im.save(a, quality=90)
    _near_copy(a, b)

    fa = compute_fingerprint(a)
    fb = compute_fingerprint(b)
    assert fa and fb
    # With threshold 14 + consensus, credit-bar variant should match
    result = compare_fingerprints(fa, fb, threshold=14, consensus_slack=4)
    assert result.matched, f"expected near-dup, got {result}"


def test_different_images_not_matched(tmp_path: Path):
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    _solid(a, (10, 10, 10))
    _solid(b, (240, 240, 10))
    with Image.open(a) as im:
        ImageDraw.Draw(im).rectangle([0, 0, 100, 100], fill=(255, 0, 0))
        im.save(a)
    with Image.open(b) as im:
        ImageDraw.Draw(im).ellipse([200, 100, 500, 300], fill=(0, 0, 255))
        im.save(b)
    fa, fb = compute_fingerprint(a), compute_fingerprint(b)
    assert fa and fb
    result = compare_fingerprints(fa, fb, threshold=14, consensus_slack=4)
    assert not result.matched


def test_parse_legacy_and_v2_cache():
    legacy = parse_cache_line("949a98181a917040")
    assert legacy and legacy.dhash == "949a98181a917040"
    v2 = parse_cache_line("aaa bbb ccc /tmp/x.jpg")
    assert v2 and v2.phash == "bbb" and v2.path == "/tmp/x.jpg"


def test_library_index_and_groups(tmp_path: Path):
    lib = tmp_path / "Wallpapers"
    lib.mkdir()
    a = lib / "one.jpg"
    b = lib / "one_copy.jpg"
    c = lib / "other.jpg"
    with Image.new("RGB", (800, 450), (30, 60, 90)) as im:
        ImageDraw.Draw(im).rectangle([100, 50, 400, 300], fill=(200, 50, 50))
        im.save(a, quality=90)
    _near_copy(a, b)
    with Image.new("RGB", (800, 450), (200, 200, 50)) as im:
        ImageDraw.Draw(im).ellipse([50, 50, 700, 400], fill=(10, 10, 10))
        im.save(c, quality=90)

    ops = OpsConfig()
    ops.wallpaper_dir = str(lib)
    ops.hash_cache = str(tmp_path / "hashes")
    ops.perceptual_hash_threshold = 14

    idx = LibraryIndex(ops)
    entries = idx.ensure_loaded(progress=False)
    assert len(entries) >= 3

    # undup groups should find a+b
    groups, n = find_duplicate_groups(lib, threshold=14, consensus_slack=4, progress=False)
    assert n == 3
    assert any(len(g["paths"]) >= 2 for g in groups)
