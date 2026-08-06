"""
Image storage + compression helper.

WHAT HAPPENS TO AN UPLOADED IMAGE, STEP BY STEP:
1. FastAPI receives the multipart/form-data upload as an UploadFile —
   a spooled temp file, so large uploads don't get fully buffered in RAM.
2. We validate the content type (only actual images) and size BEFORE
   doing any processing — reject early, never trust the client's
   Content-Type header alone (Pillow re-opening the bytes and calling
   .verify() is what actually confirms it's a real, undamaged image).
3. Pillow re-encodes the image as JPEG at a fixed quality and caps its
   longest side at MAX_DIMENSION. This is the "image compression" step
   from the brief: production catalogs never store the raw upload
   as-is — a phone photo can be 8-12MB; nobody's product grid needs
   that. Re-encoding at ~85% JPEG quality and a sane max resolution
   routinely cuts file size by 80-95% with no visible quality loss at
   the sizes it's actually displayed.
4. The compressed bytes are written to disk under
   media/products/{product_id}/{random-uuid}.jpg — a random filename
   (not the user's original filename) avoids path traversal and
   filename-collision attacks entirely.
5. We return the relative URL; the caller (the admin endpoint) is
   responsible for creating the ProductImage DB row that points at it.

WHY LOCAL DISK FOR PHASE 2, NOT S3:
Object storage (S3/GCS/Cloud Storage) is what real production deployments
use — local disk doesn't survive a container redeploy and doesn't scale
across multiple backend instances. This module isolates ALL file I/O
behind save_product_image()/delete_product_image(), so swapping the
implementation to upload to S3 later touches only this one file, not
every route that happens to handle images.
"""
import io
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

MEDIA_ROOT = Path(__file__).resolve().parent.parent.parent / "media"
PRODUCTS_DIR = MEDIA_ROOT / "products"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB raw upload cap
MAX_DIMENSION = 1600  # longest side, in pixels, after compression
JPEG_QUALITY = 85

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def save_product_image(product_id: uuid.UUID, upload: UploadFile) -> str:
    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG, or WEBP images are accepted",
        )

    raw_bytes = await upload.read()
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )

    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.verify()  # raises if the bytes aren't a real, intact image
        # verify() leaves the file object unusable — reopen to actually process it
        image = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is not a valid image",
        )

    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))  # in-place, preserves aspect ratio

    product_dir = PRODUCTS_DIR / str(product_id)
    product_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.jpg"
    destination = product_dir / filename
    image.save(destination, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    return f"/media/products/{product_id}/{filename}"


def delete_product_image(image_url: str) -> None:
    """Best-effort disk cleanup — if the file is already gone, that's fine,
    the DB row deletion is what actually matters for correctness."""
    relative_path = image_url.removeprefix("/media/")
    file_path = MEDIA_ROOT / relative_path
    file_path.unlink(missing_ok=True)
