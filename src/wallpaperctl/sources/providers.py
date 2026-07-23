"""Remote wallpaper providers: Unsplash, Pexels, Pixabay."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx

from wallpaperctl.config import ApiConfig
from wallpaperctl.util import log_error, url_encode_spaces

log = logging.getLogger("wallpaperctl")

PIXABAY_CATEGORIES = {
    "backgrounds",
    "fashion",
    "nature",
    "science",
    "education",
    "feelings",
    "health",
    "people",
    "religion",
    "places",
    "animals",
    "industry",
    "computer",
    "food",
    "sports",
    "transportation",
    "travel",
    "buildings",
    "business",
    "music",
}


@dataclass
class ProviderResult:
    image_url: str
    photographer_name: str
    photographer_username: str
    provider_name: str


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)


def fetch_unsplash(api: ApiConfig) -> ProviderResult | None:
    cats = url_encode_spaces(api.categories)
    url = (
        "https://api.unsplash.com/photos/random"
        f"?client_id={api.unsplash_access_key}"
        f"&orientation=landscape&query={cats}&w=1920&h=1080"
    )
    try:
        with _client() as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log_error(f"Unsplash fetch failed: {e}")
        return None
    try:
        raw = data["urls"]["raw"]
        image_url = f"{raw}&w=1920&h=1080&fit=crop"
        user = data.get("user") or {}
        return ProviderResult(
            image_url=image_url,
            photographer_name=user.get("name") or "Unknown Photographer",
            photographer_username=user.get("username") or "unknown",
            provider_name="Unsplash",
        )
    except (KeyError, TypeError) as e:
        log_error(f"Unsplash parse failed: {e}")
        return None


def fetch_pexels(api: ApiConfig) -> ProviderResult | None:
    query = quote_plus(api.categories.replace(",", " "))
    page = random.randint(1, 100)
    url = (
        "https://api.pexels.com/v1/search"
        f"?query={query}&orientation=landscape&per_page=1&page={page}"
    )
    try:
        with _client() as client:
            r = client.get(url, headers={"Authorization": api.pexels_api_key})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log_error(f"Pexels fetch failed: {e}")
        return None
    try:
        photo = data["photos"][0]
        return ProviderResult(
            image_url=photo["src"]["large2x"],
            photographer_name=photo.get("photographer") or "Unknown Photographer",
            photographer_username=photo.get("photographer") or "unknown",
            provider_name="Pexels",
        )
    except (KeyError, IndexError, TypeError) as e:
        log_error(f"Pexels parse failed: {e}")
        return None


def fetch_pixabay(api: ApiConfig) -> ProviderResult | None:
    primary = api.categories.split(",")[0].strip()
    page = random.randint(1, 50)
    params = {
        "key": api.pixabay_api_key,
        "image_type": "photo",
        "orientation": "horizontal",
        "min_width": 1920,
        "min_height": 1080,
        "per_page": 10,
        "page": page,
    }
    if primary in PIXABAY_CATEGORIES:
        params["category"] = primary
        params["q"] = ""
    else:
        params["q"] = primary

    try:
        with _client() as client:
            r = client.get("https://pixabay.com/api/", params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log_error(f"Pixabay fetch failed: {e}")
        return None
    hits = data.get("hits") or []
    if not hits:
        log_error("Pixabay found no images for query. Try different categories.")
        return None
    hit = random.choice(hits[:10])
    return ProviderResult(
        image_url=hit.get("largeImageURL") or "",
        photographer_name=hit.get("user") or "Unknown Photographer",
        photographer_username=hit.get("user") or "unknown",
        provider_name="Pixabay",
    )


def pick_provider(tried: set[str]) -> str:
    """Weighted: Unsplash 60%, Pexels 30%, Pixabay 10% among untried."""
    order = [("unsplash", 60), ("pexels", 30), ("pixabay", 10)]
    available = [name for name, _ in order if name not in tried]
    if not available:
        return random.choice(["unsplash", "pexels", "pixabay"])
    weights = [w for name, w in order if name in available]
    return random.choices(available, weights=weights, k=1)[0]


def fetch_from_provider(name: str, api: ApiConfig) -> ProviderResult | None:
    if name == "unsplash":
        return fetch_unsplash(api)
    if name == "pexels":
        return fetch_pexels(api)
    if name == "pixabay":
        return fetch_pixabay(api)
    return None
