"""Provider query helpers and pagination clamping."""

from __future__ import annotations

from wallpaperctl.config import ApiConfig
from wallpaperctl.sources.providers import category_terms, pick_query


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
