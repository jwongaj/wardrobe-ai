import io
import gc
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# Strictly 1 worker to prevent concurrent RAM spikes on Render's 512MB tier
_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_REMBG_SESSION = None

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


def _get_rembg_session():
    """Lazy-load the lightweight u2netp model (~4MB) on demand."""
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        try:
            from rembg import new_session
            _REMBG_SESSION = new_session("u2netp")
        except Exception as e:
            print(f"Warning: Failed to load rembg u2netp session: {e}")
            _REMBG_SESSION = None
    return _REMBG_SESSION


def crop_and_isolate_garment(
    image_bytes: bytes,
    box_2d: list,
    garment_type: str = "top",
    primary_color: str = "",
    is_accessory: bool = False
) -> bytes:
    """
    Memory-safe precision cropping and background isolation.
    Guarantees white/cream/linen garments remain completely opaque.
    """
    # 1. Load image and normalize EXIF orientation
    pil_img = Image.open(io.BytesIO(image_bytes))
    try:
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception:
        pass

    pil_img = pil_img.convert("RGB")
    
    # 2. Downscale the source image to max 1024px to prevent large coordinate buffers
    w, h = pil_img.size
    if max(w, h) > 1024:
        scale = 1024.0 / float(max(w, h))
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
        w, h = pil_img.size

    # box_2d: [ymin, xmin, ymax, xmax] normalized on a 0-1000 scale
    ymin, xmin, ymax, xmax = box_2d
    top = int((ymin / 1000.0) * h)
    left = int((xmin / 1000.0) * w)
    bottom = int((ymax / 1000.0) * h)
    right = int((xmax / 1000.0) * w)

    box_w = max(10, right - left)
    box_h = max(10, bottom - top)

    # Padding calculation
    pad_ratio_x = 0.12 if not is_accessory else 0.20
    pad_ratio_y = 0.10 if not is_accessory else 0.15

    pad_x = int(box_w * pad_ratio_x)
    pad_y = int(box_h * pad_ratio_y)

    crop_top = max(0, top - pad_y)
    crop_left = max(0, left - pad_x)
    crop_bottom = min(h, bottom + pad_y)
    crop_right = min(w, right + pad_x)

    cropped_pil = pil_img.crop((crop_left, crop_top, crop_right, crop_bottom))
    
    # 3. Downscale the cropped segment to max 800px before rembg processing
    cw, ch = cropped_pil.size
    if max(cw, ch) > 800:
        scale = 800.0 / float(max(cw, ch))
        cropped_pil = cropped_pil.resize((int(cw * scale), int(ch * scale)), Image.Resampling.BILINEAR)
        cw, ch = cropped_pil.size

    orig_rgb = np.array(cropped_pil, dtype=np.uint8)

    buf_in = io.BytesIO()
    cropped_pil.save(buf_in, format="PNG")
    cropped_bytes = buf_in.getvalue()

    is_white_item = any(
        w_name in primary_color.lower()
        for w_name in ["white", "ivory", "cream", "linen", "light", "beige", "oatmeal"]
    )

    try:
        from rembg import remove

        session = _get_rembg_session()
        mask_bytes = remove(
            cropped_bytes,
            session=session,
            alpha_matting=False,
            only_mask=True
        )

        mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
        if mask_img.size != (cw, ch):
            mask_img = mask_img.resize((cw, ch), Image.Resampling.BILINEAR)

        mask_np = np.array(mask_img, dtype=np.uint8)
        foreground_ratio = np.count_nonzero(mask_np > 25) / float(cw * ch)

        if is_white_item and foreground_ratio < 0.30:
            solid_mask = np.full((ch, cw), 255, dtype=np.uint8)
        else:
            _, binary_mask = cv2.threshold(mask_np, 20, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            solid_mask = np.zeros_like(binary_mask)

            if contours:
                contours = sorted(contours, key=cv2.contourArea, reverse=True)
                main_area = cv2.contourArea(contours[0])
                valid_contours = [c for c in contours if cv2.contourArea(c) >= (main_area * 0.05)]
                cv2.drawContours(solid_mask, valid_contours, -1, 255, thickness=cv2.FILLED)
            else:
                solid_mask = binary_mask

        r, g, b = orig_rgb[:, :, 0], orig_rgb[:, :, 1], orig_rgb[:, :, 2]
        rgba_out = np.dstack((r, g, b, solid_mask))
        final_pil = Image.fromarray(rgba_out, mode="RGBA")

    except Exception as ex:
        print(f"rembg isolation fallback: {ex}")
        final_pil = cropped_pil

    buf_out = io.BytesIO()
    final_pil.save(buf_out, format="PNG", optimize=True)

    # 4. Immediate Garbage Collection to free RAM
    del orig_rgb
    gc.collect()

    return buf_out.getvalue()


async def async_crop_and_isolate_garment(
    image_bytes: bytes,
    box_2d: list,
    garment_type: str = "top",
    primary_color: str = "",
    is_accessory: bool = False
) -> bytes:
    """Non-blocking async runner bounded to a single executor thread."""
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
    """Rotates an image clockwise while preserving RGBA transparency."""
    pil_img = Image.open(io.BytesIO(image_bytes))
    rotated_img = pil_img.rotate(-degrees, expand=True)
    buf_out = io.BytesIO()
    fmt = "PNG" if pil_img.mode == "RGBA" else "JPEG"
    rotated_img.save(buf_out, format=fmt)
    return buf_out.getvalue()