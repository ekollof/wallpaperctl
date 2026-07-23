"""Remote wallpaper providers: Unsplash, Pexels, Pixabay.

API base URLs (still current as of 2026):
  * Unsplash  GET https://api.unsplash.com/photos/random
  * Pexels    GET https://api.pexels.com/v1/search
  * Pixabay   GET https://pixabay.com/api/

Note: Unsplash returns HTTP 404 with ``{"errors":["No photos found."]}`` when a
query matches nothing — that is *not* a wrong endpoint. Always search with a
single category term, not the full comma-separated CATEGORIES string.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

import httpx

from wallpaperctl.config import ApiConfig
from wallpaperctl.util import log_error

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

# Pixabay free tier exposes at most 500 hits per query.
PIXABAY_MAX_HITS = 500


@dataclass
class ProviderResult:
    image_url: str
    photographer_name: str
    photographer_username: str
    provider_name: str


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)


def category_terms(api: ApiConfig) -> list[str]:
    """Split CATEGORIES into individual search terms."""
    terms = [c.strip() for c in (api.categories or "").split(",") if c.strip()]
    return terms or ["nature"]


def pick_query(api: ApiConfig) -> str:
    """One random term — providers treat multi-term AND queries poorly."""
    return random.choice(category_terms(api))


def _http_error_detail(resp: httpx.Response) -> str:
    """Short body snippet for logs (Unsplash 404 == no results, not bad URL)."""
    try:
        text = resp.text.strip().replace("\n", " ")
        return text[:200] if text else resp.reason_phrase
    except Exception:
        return resp.reason_phrase


def _shuffled_queries(api: ApiConfig, *, limit: int = 4) -> list[str]:
    """Up to `limit` distinct category terms, shuffled for variety."""
    terms = category_terms(api)
    random.shuffle(terms)
    return terms[: max(1, limit)]


def fetch_unsplash(api: ApiConfig) -> ProviderResult | None:
    """GET /photos/random — auth via Authorization: Client-ID <key>."""
    url = "https://api.unsplash.com/photos/random"
    headers = {
        "Authorization": f"Client-ID {api.unsplash_access_key}",
        "Accept-Version": "v1",
    }
    last_err = "no queries"
    try:
        with _client() as client:
            for query in _shuffled_queries(api):
                params = {"orientation": "landscape", "query": query}
                r = client.get(url, headers=headers, params=params)
                if r.status_code == 404:
                    # Unsplash uses 404 for "no photos found" for this query.
                    last_err = f"no photos for query={query!r} ({_http_error_detail(r)})"
                    log.debug("Unsplash: %s", last_err)
                    continue
                r.raise_for_status()
                data = r.json()
                # CDN resize params belong on the image URL, not the API query.
                raw = data["urls"]["raw"]
                image_url = f"{raw}&w=1920&h=1080&fit=crop"
                user = data.get("user") or {}
                return ProviderResult(
                    image_url=image_url,
                    photographer_name=user.get("name") or "Unknown Photographer",
                    photographer_username=user.get("username") or "unknown",
                    provider_name="Unsplash",
                )
    except Exception as e:
        log_error(f"Unsplash fetch failed: {e}")
        return None
    log_error(f"Unsplash: {last_err}")
    return None


def fetch_pexels(api: ApiConfig) -> ProviderResult | None:
    """GET /v1/search — auth via Authorization: <api_key>."""
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": api.pexels_api_key}
    last_query = ""
    try:
        with _client() as client:
            for query in _shuffled_queries(api):
                last_query = query
                # Stay on early pages; deep pages of niche queries are often empty.
                page = random.randint(1, 20)
                params = {
                    "query": query,
                    "orientation": "landscape",
                    "per_page": 15,
                    "page": page,
                }
                r = client.get(url, headers=headers, params=params)
                r.raise_for_status()
                data = r.json()
                photos = data.get("photos") or []
                if not photos and page != 1:
                    params["page"] = 1
                    r = client.get(url, headers=headers, params=params)
                    r.raise_for_status()
                    data = r.json()
                    photos = data.get("photos") or []
                if not photos:
                    log.debug("Pexels: no photos for query=%r", query)
                    continue
                photo = random.choice(photos)
                return ProviderResult(
                    image_url=photo["src"]["large2x"],
                    photographer_name=photo.get("photographer")
                    or "Unknown Photographer",
                    photographer_username=photo.get("photographer") or "unknown",
                    provider_name="Pexels",
                )
    except Exception as e:
        log_error(f"Pexels fetch failed: {e}")
        return None
    log_error(f"Pexels: no photos for query={last_query!r}")
    return None


def fetch_pixabay(api: ApiConfig) -> ProviderResult | None:
    """GET https://pixabay.com/api/ — key as query param."""
    per_page = 20
    last_query = ""
    try:
        with _client() as client:
            for query in _shuffled_queries(api):
                last_query = query
                params: dict = {
                    "key": api.pixabay_api_key,
                    "image_type": "photo",
                    "orientation": "horizontal",
                    "min_width": 1920,
                    "min_height": 1080,
                    "per_page": per_page,
                    "safesearch": "true",
                    "page": 1,
                }
                # Official named categories vs free-text q.
                if query.lower() in PIXABAY_CATEGORIES:
                    params["category"] = query.lower()
                    params["q"] = ""
                else:
                    params["q"] = query

                # Page 1 first so we know totalHits and never request empty pages.
                r = client.get("https://pixabay.com/api/", params=params)
                r.raise_for_status()
                data = r.json()
                total_hits = int(data.get("totalHits") or 0)
                if total_hits <= 0:
                    log.debug("Pixabay: no hits for query=%r", query)
                    continue
                max_page = max(1, min(total_hits, PIXABAY_MAX_HITS) // per_page)
                if max_page > 1:
                    params["page"] = random.randint(1, max_page)
                    r = client.get("https://pixabay.com/api/", params=params)
                    r.raise_for_status()
                    data = r.json()
                hits = data.get("hits") or []
                if not hits:
                    # Race / empty page — use first page from earlier if needed.
                    params["page"] = 1
                    r = client.get("https://pixabay.com/api/", params=params)
                    r.raise_for_status()
                    hits = (r.json().get("hits") or [])
                if not hits:
                    continue
                hit = random.choice(hits)
                image_url = hit.get("largeImageURL") or hit.get("webformatURL") or ""
                if not image_url:
                    continue
                return ProviderResult(
                    image_url=image_url,
                    photographer_name=hit.get("user") or "Unknown Photographer",
                    photographer_username=hit.get("user") or "unknown",
                    provider_name="Pixabay",
                )
    except Exception as e:
        log_error(f"Pixabay fetch failed: {e}")
        return None
    log_error(
        f"Pixabay found no images for query={last_query!r}. "
        "Try different categories."
    )
    return None



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
