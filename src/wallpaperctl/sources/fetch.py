"""Orchestrate remote wallpaper fetch, dedup, optimize."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from wallpaperctl.config import ApiConfig, OpsConfig
from wallpaperctl.sources import dedup, optimize, providers
from wallpaperctl.sources.optimize import is_image
from wallpaperctl.util import log_error, sanitize_string


log = logging.getLogger("wallpaperctl")


@dataclass
class FetchResult:
    path: Path
    photographer_name: str
    photographer_username: str
    provider_name: str


def fetch_random_wallpaper(
    api: ApiConfig,
    ops: OpsConfig | None = None,
) -> FetchResult | None:
    ops = ops or OpsConfig()
    wall_dir = ops.path("wallpaper_dir")
    wall_dir.mkdir(parents=True, exist_ok=True)
    url_log = ops.path("url_log")
    max_attempts = ops.fetch_max_attempts
    index: dedup.LibraryIndex | None = None

    tried: set[str] = set()
    for attempt in range(1, max_attempts + 1):
        print(
            f"Attempt {attempt} of {max_attempts} to fetch near-16:9 wallpaper "
            f"with categories '{api.categories}'...",
            file=sys.stderr,
        )
        provider_key = providers.pick_provider(tried)
        tried.add(provider_key)
        result = providers.fetch_from_provider(provider_key, api)
        if not result or not result.image_url:
            log_error(f"Failed to get image URL from {provider_key}")
            continue

        if dedup.is_url_duplicate(result.image_url, result.provider_name, url_log):
            log.debug("URL duplicate from %s, retrying", result.provider_name)
            continue

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        base = (
            f"{ts}_{sanitize_string(result.photographer_name)}_"
            f"{sanitize_string(result.photographer_username)}_"
            f"{sanitize_string(result.provider_name)}"
        )
        temp = wall_dir / f"{base}.jpg"
        optimized = wall_dir / f"{base}_opt.jpg"

        if not _download(result.image_url, temp, result.provider_name):
            temp.unlink(missing_ok=True)
            continue

        if not is_image(temp):
            log_error(f"Downloaded file from {result.provider_name} is not a valid image")
            temp.unlink(missing_ok=True)
            continue


        if not dedup.check_aspect_ratio(temp, ops):
            print(
                f"Image from {result.provider_name} is not near-16:9, retrying...",
                file=sys.stderr,
            )
            temp.unlink(missing_ok=True)
            continue

        # Build / refresh library index once per fetch session so we compare
        # against *all* of ~/Wallpapers (not only a thin URL cache).
        if index is None:
            index = dedup.LibraryIndex(ops)
            print("Building perceptual index of wallpaper library…", file=sys.stderr)
            index.ensure_loaded(progress=True)

        # Hash after a quick open of the download; also re-check post-optimize
        # below so resize-normalized forms match the library.
        match = index.is_duplicate(temp)
        if match.matched:
            print(
                f"Skipping perceptual duplicate from {result.provider_name} "
                f"({match.reason}"
                + (f", dist={match.distance}" if match.distance is not None else "")
                + ")",
                file=sys.stderr,
            )
            temp.unlink(missing_ok=True)
            continue

        dedup.log_url(result.image_url, result.provider_name, url_log)
        optimize.optimize_image(
            temp,
            optimized,
            width=ops.target_width,
            height=ops.target_height,
        )
        if not optimized.is_file():
            log_error("Optimized wallpaper was not created")
            continue

        # Second check on the resized frame (library images are usually 1920x1080)
        match2 = index.is_duplicate(optimized)
        if match2.matched:
            print(
                f"Skipping optimized duplicate from {result.provider_name} "
                f"({match2.reason})",
                file=sys.stderr,
            )
            optimized.unlink(missing_ok=True)
            continue

        index.add(optimized)

        return FetchResult(
            path=optimized,
            photographer_name=result.photographer_name,
            photographer_username=result.photographer_username,
            provider_name=result.provider_name,
        )


    log_error(
        f"Failed to fetch a near-16:9 wallpaper after {max_attempts} attempts"
    )
    return None


def _download(url: str, dest: Path, provider: str) -> bool:
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True) as client:
            with client.stream("GET", url) as r:
                r.raise_for_status()
                with dest.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
        return True
    except Exception as e:
        log_error(f"Failed to download wallpaper from {provider}: {e}")
        return False


