"""Image resize/crop and photographer credit overlay (Pillow only)."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

log = logging.getLogger("wallpaperctl")

# Preferred monospaced fonts for credit overlay (Linux + BSD paths)
_FONT_CANDIDATES = (
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/local/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/usr/X11R6/lib/X11/fonts/TTF/DejaVuSansMono.ttf",  # OpenBSD
    "/usr/local/share/fonts/dejavu/DejaVuSansMono.ttf",  # FreeBSD
)


def is_image(path: Path) -> bool:
    """True if Pillow can open and decode the file as an image."""
    try:
        with Image.open(path) as img:
            img.load()
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False



def image_size(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as img:
            return img.size
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def optimize_image(
    src: Path,
    dest: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    quality: int = 85,
) -> Path:
    """Cover-crop to width×height and save as JPEG (mirrors ImageMagick resize^ + crop)."""
    try:
        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)
            fitted = ImageOps.fit(
                img,
                (width, height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            if fitted.mode not in ("RGB", "L"):
                fitted = fitted.convert("RGB")
            elif fitted.mode == "L":
                fitted = fitted.convert("RGB")
            dest.parent.mkdir(parents=True, exist_ok=True)
            fitted.save(dest, format="JPEG", quality=quality, optimize=True)
    except Exception as e:
        log.warning("Failed to optimize image with Pillow (%s), using original", e)
        return _fallback_to_dest(src, dest)

    if not dest.is_file() or not is_image(dest):
        log.warning("Optimized image invalid, using original")
        dest.unlink(missing_ok=True)
        return _fallback_to_dest(src, dest)

    src.unlink(missing_ok=True)
    return dest


def _fallback_to_dest(src: Path, dest: Path) -> Path:
    import shutil

    if src.resolve() == dest.resolve():
        return dest
    if src.is_file():
        shutil.move(str(src), str(dest))
    return dest



def add_credits(
    image_path: Path,
    photographer_name: str,
    photographer_username: str,
    provider_name: str,
) -> Path:
    """Draw a SouthEast credit bar (white text on semi-transparent black)."""
    if not photographer_name or not photographer_username or not provider_name:
        log.warning("Missing credit info, skipping overlay")
        return image_path

    if provider_name == "Unsplash":
        credit = f"Photo by {photographer_name} (@{photographer_username}) on Unsplash"
    elif provider_name == "Pexels":
        credit = f"Photo by {photographer_name} on Pexels"
    elif provider_name == "Pixabay":
        credit = f"Image by {photographer_name} from Pixabay"
    else:
        credit = f"Photo by {photographer_name} (Source: {provider_name})"

    # Match old ImageMagick padding around the label
    text = f" {credit} "

    name = image_path.name
    if name.endswith("_opt.jpg"):
        credited = image_path.with_name(name[: -len("_opt.jpg")] + "_credited.jpg")
    else:
        credited = image_path.with_name(image_path.stem + "_credited.jpg")

    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGBA":
                base = img.convert("RGBA")
            else:
                base = img.copy()

            overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            font = _load_font(18)

            # textbbox is more accurate than textsize (removed in newer Pillow)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            margin = 20
            pad_x, pad_y = 4, 3
            x1 = base.width - margin - tw - pad_x * 2
            y1 = base.height - margin - th - pad_y * 2
            x2 = base.width - margin
            y2 = base.height - margin

            # undercolor rgba(0,0,0,0.5)
            draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0, 128))
            draw.text(
                (x1 + pad_x, y1 + pad_y),
                text,
                font=font,
                fill=(255, 255, 255, 255),
            )

            composed = Image.alpha_composite(base, overlay).convert("RGB")
            composed.save(credited, format="JPEG", quality=90, optimize=True)
    except Exception as e:
        log.warning("Failed to add credits with Pillow (%s), using original", e)
        credited.unlink(missing_ok=True)
        return image_path

    if not credited.is_file() or not is_image(credited):
        log.warning("Credited image invalid, using original")
        credited.unlink(missing_ok=True)
        return image_path

    image_path.unlink(missing_ok=True)
    log.debug("Credits added: %s", credited)
    return credited


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            if Path(path).is_file():
                return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    # Last resort: bitmap default (not mono, but works without system fonts)
    log.debug("DejaVu Sans Mono not found; using Pillow default font")
    try:
        return ImageFont.load_default(size=size)  # Pillow ≥10.1
    except TypeError:
        return ImageFont.load_default()
