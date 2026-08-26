"""Remote wallpaper providers: Unsplash, Pexels, Pixabay.

API base URLs (still current as of 2026):
  * Unsplash  GET https://api.unsplash.com/photos/random
  * Pexels    GET https://api.pexels.com/v1/search
  * Pixabay   GET https://pixabay.com/api/

Animated (video) variants, same API keys:
  * Pexels    GET https://api.pexels.com/v1/videos/search
  * Pixabay   GET https://pixabay.com/api/videos/

Note: Unsplash returns HTTP 404 with ``{"errors":["No photos found."]}`` when a
query matches nothing — that is *not* a wrong endpoint. Always search with a
single category term, not the full comma-separated CATEGORIES string.
"""

from __future__ import annotations

import logging
import random
import re
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
    # Human-readable tags / alt text from the provider (may be empty).
    tags: str = ""


@dataclass
class VideoResult:
    video_url: str
    width: int
    height: int
    photographer_name: str
    photographer_username: str
    provider_name: str
    tags: str = ""


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)


def category_terms(api: ApiConfig) -> list[str]:
    """Split CATEGORIES into individual search terms."""
    terms = [c.strip() for c in (api.categories or "").split(",") if c.strip()]
    return terms or ["nature"]


def exclude_terms(api: ApiConfig) -> list[str]:
    """Split EXCLUDE_KEYWORDS into lowercase needles for client-side filtering."""
    return [
        t.strip().lower()
        for t in (api.exclude_keywords or "").split(",")
        if t.strip()
    ]


def matches_exclude(*parts: object, api: ApiConfig) -> bool:
    """True if any exclude term appears as a substring in the joined text.

    Providers do not support server-side negative keywords; we filter hits
    using tags / alt / description when present.
    """
    terms = exclude_terms(api)
    if not terms:
        return False
    blob = " ".join(str(p) for p in parts if p).lower()
    if not blob:
        return False
    return any(term in blob for term in terms)


def _choose_unexcluded(
    items: list,
    api: ApiConfig,
    text_fn,
) -> object | None:
    """Shuffle *items* and return the first that does not match excludes."""
    if not items:
        return None
    if not exclude_terms(api):
        return random.choice(items)
    shuffled = list(items)
    random.shuffle(shuffled)
    for item in shuffled:
        if not matches_exclude(*text_fn(item), api=api):
            return item
    log.debug(
        "All %d hit(s) matched EXCLUDE_KEYWORDS=%r",
        len(items),
        api.exclude_keywords,
    )
    return None


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


def _unsplash_text(data: dict) -> tuple[str, ...]:
    tags = data.get("tags") or []
    tag_titles = []
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, dict):
                tag_titles.append(str(t.get("title") or ""))
            else:
                tag_titles.append(str(t))
    return (
        data.get("description") or "",
        data.get("alt_description") or "",
        " ".join(tag_titles),
    )


def _pexels_slug_title(url: str) -> str:
    """Human title from a Pexels page URL slug.

    Example: ``.../video/plants-by-the-river-1208094/`` → ``plants by the river``.
    Video ``tags`` is often an empty list; the slug is the useful text.
    """
    if not url:
        return ""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"-\d+$", "", slug)
    return slug.replace("-", " ").strip()


def _pexels_photo_text(photo: dict) -> tuple[str, ...]:
    return (
        photo.get("alt") or "",
        _pexels_slug_title(str(photo.get("url") or "")),
    )


def _pexels_video_text(video: dict) -> tuple[str, ...]:
    raw_tags = video.get("tags") or []
    if isinstance(raw_tags, list):
        tag_str = ", ".join(str(t) for t in raw_tags if t)
    else:
        tag_str = str(raw_tags)
    return (
        tag_str,
        _pexels_slug_title(str(video.get("url") or "")),
    )


def _pixabay_text(hit: dict) -> tuple[str, ...]:
    return (hit.get("tags") or "",)


def _display_tags(*parts: object) -> str:
    """Normalize provider tag/alt fragments into a comma-separated label."""
    seen: list[str] = []
    for part in parts:
        if not part:
            continue
        text = str(part).strip()
        if not text:
            continue
        # Pixabay already uses commas; alt text is usually one phrase.
        for piece in text.replace(";", ",").split(","):
            piece = piece.strip()
            if piece and piece.lower() not in {s.lower() for s in seen}:
                seen.append(piece)
    return ", ".join(seen)


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
                if matches_exclude(*_unsplash_text(data), api=api):
                    log.debug(
                        "Unsplash: excluded hit for query=%r (%r)",
                        query,
                        api.exclude_keywords,
                    )
                    continue
                # CDN resize params belong on the image URL, not the API query.
                raw = data["urls"]["raw"]
                image_url = f"{raw}&w=1920&h=1080&fit=crop"
                user = data.get("user") or {}
                return ProviderResult(
                    image_url=image_url,
                    photographer_name=user.get("name") or "Unknown Photographer",
                    photographer_username=user.get("username") or "unknown",
                    provider_name="Unsplash",
                    tags=_display_tags(*_unsplash_text(data)),
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
                photo = _choose_unexcluded(photos, api, _pexels_photo_text)
                if photo is None:
                    continue
                assert isinstance(photo, dict)
                return ProviderResult(
                    image_url=photo["src"]["large2x"],
                    photographer_name=photo.get("photographer")
                    or "Unknown Photographer",
                    photographer_username=photo.get("photographer") or "unknown",
                    provider_name="Pexels",
                    tags=_display_tags(*_pexels_photo_text(photo)),
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
                hit = _choose_unexcluded(hits, api, _pixabay_text)
                if hit is None:
                    continue
                assert isinstance(hit, dict)
                image_url = hit.get("largeImageURL") or hit.get("webformatURL") or ""
                if not image_url:
                    continue
                return ProviderResult(
                    image_url=image_url,
                    photographer_name=hit.get("user") or "Unknown Photographer",
                    photographer_username=hit.get("user") or "unknown",
                    provider_name="Pixabay",
                    tags=_display_tags(*_pixabay_text(hit)),
                )
    except Exception as e:
        log_error(f"Pixabay fetch failed: {e}")
        return None
    log_error(
        f"Pixabay found no images for query={last_query!r}. "
        "Try different categories."
    )
    return None



# ── Animated (video) providers ───────────────────────────────────────────

_MAX_VIDEO_SECONDS = 60


def _prefer_short(videos: list[dict]) -> list[dict]:
    """Short clips first; fall back to all when nothing qualifies."""
    short = [v for v in videos if 0 < int(v.get("duration") or 0) <= _MAX_VIDEO_SECONDS]
    return short or videos


def _pixabay_tier(hit: dict) -> dict | None:
    """Best rendition dict {url,width,height} from a Pixabay video hit."""
    tiers = hit.get("videos") or {}
    if not isinstance(tiers, dict):
        return None
    for name in ("large", "medium", "small", "tiny"):
        t = tiers.get(name) or {}
        url = t.get("url")
        if url and int(t.get("width") or 0) >= int(t.get("height") or 0):
            return {
                "url": url,
                "width": int(t.get("width") or 0),
                "height": int(t.get("height") or 0),
            }
    return None


def fetch_pexels_video(api: ApiConfig) -> VideoResult | None:
    """GET /v1/videos/search — same key/headers as the photo endpoint."""
    url = "https://api.pexels.com/v1/videos/search"
    headers = {"Authorization": api.pexels_api_key}
    last_query = ""
    try:
        with _client() as client:
            for query in _shuffled_queries(api):
                last_query = query
                page = random.randint(1, 10)
                params = {
                    "query": query,
                    "orientation": "landscape",
                    "per_page": 15,
                    "page": page,
                }
                r = client.get(url, headers=headers, params=params)
                r.raise_for_status()
                data = r.json()
                videos = data.get("videos") or []
                if not videos and page != 1:
                    params["page"] = 1
                    r = client.get(url, headers=headers, params=params)
                    r.raise_for_status()
                    data = r.json()
                    videos = data.get("videos") or []
                if not videos:
                    log.debug("Pexels video: no results for query=%r", query)
                    continue
                video = _choose_unexcluded(
                    _prefer_short(videos), api, _pexels_video_text
                )
                if video is None:
                    continue
                assert isinstance(video, dict)
                files = [
                    f
                    for f in video.get("video_files") or []
                    if f.get("file_type") == "video/mp4" and f.get("link")
                ]
                if not files:
                    continue

                def rank(f: dict) -> tuple[int, int]:
                    w = int(f.get("width") or 0)
                    h = int(f.get("height") or 0)
                    landscape_first = 0 if w >= h else 1
                    # Closest to 1080p keeps files sane; 4K/SD lose.
                    return (landscape_first, abs(h - 1080))

                files.sort(key=rank)
                chosen = files[0]
                user = video.get("user") or {}
                return VideoResult(
                    video_url=chosen["link"],
                    width=int(chosen.get("width") or 0),
                    height=int(chosen.get("height") or 0),
                    photographer_name=user.get("name") or "Unknown Photographer",
                    photographer_username=user.get("name") or "unknown",
                    provider_name="Pexels",
                    tags=_display_tags(*_pexels_video_text(video)),
                )
    except Exception as e:
        log_error(f"Pexels video fetch failed: {e}")
        return None
    log_error(f"Pexels: no videos for query={last_query!r}")
    return None


def fetch_pixabay_video(api: ApiConfig) -> VideoResult | None:
    """GET https://pixabay.com/api/videos/ — key as query param."""
    per_page = 20
    last_query = ""
    try:
        with _client() as client:
            for query in _shuffled_queries(api):
                last_query = query
                params: dict = {
                    "key": api.pixabay_api_key,
                    "safesearch": "true",
                    "per_page": per_page,
                    "page": 1,
                }
                if query.lower() in PIXABAY_CATEGORIES:
                    params["category"] = query.lower()
                else:
                    params["q"] = query

                r = client.get("https://pixabay.com/api/videos/", params=params)
                r.raise_for_status()
                data = r.json()
                total_hits = int(data.get("totalHits") or 0)
                if total_hits <= 0:
                    log.debug("Pixabay video: no hits for query=%r", query)
                    continue
                max_page = max(1, min(total_hits, PIXABAY_MAX_HITS) // per_page)
                if max_page > 1:
                    params["page"] = random.randint(1, max_page)
                    r = client.get("https://pixabay.com/api/videos/", params=params)
                    r.raise_for_status()
                    data = r.json()
                hits = [h for h in (data.get("hits") or []) if _pixabay_tier(h)]
                if not hits:
                    continue
                hit = _choose_unexcluded(_prefer_short(hits), api, _pixabay_text)
                if hit is None:
                    continue
                assert isinstance(hit, dict)
                tier = _pixabay_tier(hit)
                assert tier is not None
                return VideoResult(
                    video_url=tier["url"],
                    width=tier["width"],
                    height=tier["height"],
                    photographer_name=hit.get("user") or "Unknown Photographer",
                    photographer_username=hit.get("user") or "unknown",
                    provider_name="Pixabay",
                    tags=_display_tags(*_pixabay_text(hit)),
                )
    except Exception as e:
        log_error(f"Pixabay video fetch failed: {e}")
        return None
    log_error(f"Pixabay found no videos for query={last_query!r}.")
    return None


def pick_video_provider(tried: set[str]) -> str:
    """Weighted: Pexels 70%, Pixabay 30% among untried."""
    order = [("pexels", 70), ("pixabay", 30)]
    available = [name for name, _ in order if name not in tried]
    if not available:
        return random.choice([name for name, _ in order])
    weights = [w for name, w in order if name in available]
    return random.choices(available, weights=weights, k=1)[0]


def fetch_video_from_provider(name: str, api: ApiConfig) -> VideoResult | None:
    if name == "pexels":
        return fetch_pexels_video(api)
    if name == "pixabay":
        return fetch_pixabay_video(api)
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
