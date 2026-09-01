import io
import gc
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# Worker pool for non-blocking execution
_EXECUTOR = ThreadPoolExecutor(max_workers=2)

# Supabase Storage Bucket Constants
STORAGE_BUCKET_NAME = "wardrobe-photos"
STORAGE_ITEMS_FOLDER = "items"
STORAGE_WORN_LOOKS_FOLDER = "worn_looks"


def get_storage_path(user_id: str, file_name: str, is_worn_look: bool = False) -> str:
    """
    Returns the organized Supabase storage path:
    - items: 'items/{user_id}/{file_name}'
    - worn_looks: 'worn_looks/{user_id}/{file_name}'
    """
    folder = STORAGE_WORN_LOOKS_FOLDER if is_worn_look else STORAGE_ITEMS_FOLDER
    return f"{folder}/{user_id}/{file_name}"


def crop_and_isolate_garment(
    image_bytes: bytes,
    box_2d: list,
    garment_type: str = "top",
    primary_color: str = "",
    is_accessory: bool = False
) -> bytes:
    """
    Ultra-fast (0.05s) precision crop using Gemini bounding coordinates.
    Zero CPU/memory bottleneck, zero timeouts.
    """
    img = None
    cropped = None
    try:
        # 1. Load image and normalize EXIF orientation
        img = Image.open(io.BytesIO(image_bytes))
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        img = img.convert("RGB")
        w, h = img.size

        # 2. Extract bounding box [ymin, xmin, ymax, xmax] (0-1000 scale)
        ymin, xmin, ymax, xmax = box_2d
        top = int((ymin / 1000.0) * h)
        left = int((xmin / 1000.0) * w)
        bottom = int((ymax / 1000.0) * h)
        right = int((xmax / 1000.0) * w)

        box_w = max(10, right - left)
        box_h = max(10, bottom - top)

        # 3. Clean proportional padding around the garment
        pad_ratio_x = 0.05 if not is_accessory else 0.08
        pad_ratio_y = 0.05 if not is_accessory else 0.08

        pad_x = int(box_w * pad_ratio_x)
        pad_y = int(box_h * pad_ratio_y)

        crop_left = max(0, left - pad_x)
        crop_top = max(0, top - pad_y)
        crop_right = min(w, right + pad_x)
        crop_bottom = min(h, bottom + pad_y)

        cropped = img.crop((crop_left, crop_top, crop_right, crop_bottom))

        # 4. Standardize max dimension for sharp closet previews without bloating storage
        cw, ch = cropped.size
        max_dim = 1024
        if max(cw, ch) > max_dim:
            scale = max_dim / float(max(cw, ch))
            cropped = cropped.resize((int(cw * scale), int(ch * scale)), Image.Resampling.LANCZOS)

        # 5. Export as optimized, high-quality JPEG
        buf_out = io.BytesIO()
        cropped.save(buf_out, format="JPEG", quality=90, optimize=True)
        return buf_out.getvalue()

    except Exception as ex:
        print(f"[CROP FALLBACK] Error cropping: {ex}", flush=True)
        return image_bytes

    finally:
        if img:
            img.close()
        if cropped:
            cropped.close()
        gc.collect()


async def async_crop_and_isolate_garment(
    image_bytes: bytes,
    box_2d: list,
    garment_type: str = "top",
    primary_color: str = "",
    is_accessory: bool = False
) -> bytes:
    """Non-blocking async wrapper."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _EXECUTOR,
        crop_and_isolate_garment,
        image_bytes,
        box_2d,
        garment_type,
        primary_color,
        is_accessory
    )


def rotate_image_bytes(image_bytes: bytes, degrees: int = 90) -> bytes:
    """Rotates an image clockwise."""
    pil_img = Image.open(io.BytesIO(image_bytes))
    try:
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception:
        pass
    rotated_img = pil_img.rotate(-degrees, expand=True)
    buf_out = io.BytesIO()
    rotated_img.save(buf_out, format="JPEG", quality=90, optimize=True)
    pil_img.close()
    rotated_img.close()
    return buf_out.getvalue()