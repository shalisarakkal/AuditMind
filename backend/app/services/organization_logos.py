"""Bounded raster decoding; stored output never contains original file metadata."""
from io import BytesIO
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD = 2 * 1024 * 1024
MAX_DIMENSION = 2048
MAX_STORED = 1024 * 1024
FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}


def normalize_logo(content: bytes, content_type: str) -> bytes:
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Logo must be at most 2 MiB")
    if content_type not in FORMATS:
        raise HTTPException(422, "Choose a PNG, JPEG or WebP image; SVG and animated images are not supported")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format != FORMATS[content_type]:
                    raise ValueError("Image format does not match its content type")
                if max(source.size) > MAX_DIMENSION or min(source.size) < 1:
                    raise ValueError("Logo dimensions must be between 1 and 2048 pixels per side")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("Animated images are not supported")
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGBA")
                image.thumbnail((512, 512), Image.Resampling.LANCZOS)
                # New image drops all source metadata, including text/EXIF/ICC.
                clean = Image.new("RGBA", image.size)
                clean.paste(image)
                output = BytesIO()
                clean.save(output, format="PNG")
                result = output.getvalue()
                if len(result) > MAX_STORED:
                    raise ValueError("Normalized logo is too large")
                return result
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as invalid:
        raise HTTPException(422, "Invalid logo: use a static PNG, JPEG or WebP up to 2048 pixels per side") from invalid
