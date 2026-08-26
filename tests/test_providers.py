"""Provider query helpers and pagination clamping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from wallpaperctl.config import ApiConfig
from wallpaperctl.sources.providers import (
    _choose_unexcluded,
    _display_tags,
    _pexels_slug_title,
    _pexels_video_text,
    category_terms,
    exclude_terms,
    fetch_pixabay,
    matches_exclude,
    pick_query,
)


def test_category_terms_split():
    api = ApiConfig(categories="cyberpunk, science fiction, anime")
    assert category_terms(api) == ["cyberpunk", "science fiction", "anime"]


def test_pick_query_is_single_term():
    api = ApiConfig(categories="cyberpunk,anime,nature")
    for _ in range(20):
        q = pick_query(api)
        assert q in {"cyberpunk", "anime", "nature"}
        assert "," not in q


def test_empty_categories_fallback():
    api = ApiConfig(categories="")
    assert category_terms(api) == ["nature"]
    assert pick_query(api) == "nature"


def test_exclude_terms_split_and_lower():
    api = ApiConfig(exclude_keywords=" People, TEXT,city ")
    assert exclude_terms(api) == ["people", "text", "city"]


def test_matches_exclude_substring():
    api = ApiConfig(exclude_keywords="people,text")
    assert matches_exclude("beautiful landscape", api=api) is False
    assert matches_exclude("crowd of people outdoors", api=api) is True
    assert matches_exclude("overlay TEXT watermark", api=api) is True


def test_choose_unexcluded_skips_matching_hits():
    api = ApiConfig(exclude_keywords="people")
    hits = [
        {"tags": "people,crowd,street"},
        {"tags": "forest,trees,moss"},
        {"tags": "more people outdoors"},
    ]
    chosen = _choose_unexcluded(hits, api, lambda h: (h["tags"],))
    assert chosen == {"tags": "forest,trees,moss"}


def test_choose_unexcluded_returns_none_when_all_match():
    api = ApiConfig(exclude_keywords="people")
    hits = [{"tags": "people,crowd"}, {"tags": "more people outdoors"}]
    assert _choose_unexcluded(hits, api, lambda h: (h["tags"],)) is None


def test_display_tags_dedupes_and_splits():
    assert _display_tags("forest, trees", "Trees", "moss;grove") == (
        "forest, trees, moss, grove"
    )
    assert _display_tags("", None) == ""


def test_pexels_slug_title_strips_id():
    assert (
        _pexels_slug_title(
            "https://www.pexels.com/video/plants-by-the-river-1208094/"
        )
        == "plants by the river"
    )
    assert (
        _pexels_slug_title(
            "https://www.pexels.com/photo/tranquil-natural-forest-with-tall-trees-33164661/"
        )
        == "tranquil natural forest with tall trees"
    )


def test_pexels_video_text_uses_slug_when_tags_empty():
    parts = _pexels_video_text(
        {
            "tags": [],
            "url": "https://www.pexels.com/video/a-pond-in-the-middle-of-a-forest-20732245/",
        }
    )
    assert _display_tags(*parts) == "a pond in the middle of a forest"


def test_pixabay_skips_excluded_tags_and_keeps_tag_label():
    api = ApiConfig(pixabay_api_key="k", categories="nature", exclude_keywords="people")
    payload = {
        "totalHits": 2,
        "hits": [
            {
                "tags": "people,crowd",
                "largeImageURL": "https://x/people.jpg",
                "user": "a",
            },
            {
                "tags": "forest, trees",
                "largeImageURL": "https://x/forest.jpg",
                "user": "b",
            },
        ],
    }
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    with patch("wallpaperctl.sources.providers._client") as client_factory:
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.get.return_value = resp
        client_factory.return_value = client
        result = fetch_pixabay(api)
    assert result is not None
    assert result.image_url == "https://x/forest.jpg"
    assert result.tags == "forest, trees"
