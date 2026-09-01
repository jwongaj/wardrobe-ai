import io
import gc
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
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
            print(f"[REMBG INIT WARNING] Failed to load u2netp session: {e}", flush=True)
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
    Memory-safe precision cropping and high-speed background isolation.
    - Caps crop at 512px for sub-2s execution on shared CPU.
    - Preserves white, cream, and linen garment opacity.
    """
    pil_img = None
    cropped_pil = None
    mask_img = None
    final_pil = None

    try:
        # 1. Load image and normalize EXIF orientation
        pil_img = Image.open(io.BytesIO(image_bytes))
        try:
            pil_img = ImageOps.exif_transpose(pil_img)
        except Exception:
            pass

        pil_img = pil_img.convert("RGB")
        w, h = pil_img.size

        # 2. Extract bounding box [ymin, xmin, ymax, xmax] (0-1000 scale)
        ymin, xmin, ymax, xmax = box_2d
        top = int((ymin / 1000.0) * h)
        left = int((xmin / 1000.0) * w)
        bottom = int((ymax / 1000.0) * h)
        right = int((xmax / 1000.0) * w)

        box_w = max(10, right - left)
        box_h = max(10, bottom - top)

        pad_ratio_x = 0.08 if not is_accessory else 0.15
        pad_ratio_y = 0.08 if not is_accessory else 0.12

        pad_x = int(box_w * pad_ratio_x)
        pad_y = int(box_h * pad_ratio_y)

        crop_top = max(0, top - pad_y)
        crop_left = max(0, left - pad_x)
        crop_bottom = min(h, bottom + pad_y)
        crop_right = min(w, right + pad_x)

        cropped_pil = pil_img.crop((crop_left, crop_top, crop_right, crop_bottom))

        # 3. Downscale crop to 512px max for fast inference
        cw, ch = cropped_pil.size
        max_dim = 512
        if max(cw, ch) > max_dim:
            scale = max_dim / float(max(cw, ch))
            cropped_pil = cropped_pil.resize((int(cw * scale), int(ch * scale)), Image.Resampling.BILINEAR)
            cw, ch = cropped_pil.size

        is_white_item = any(
            w_name in primary_color.lower()
            for w_name in ["white", "ivory", "cream", "linen", "light", "beige", "oatmeal"]
        )

        # 4. Remove background using lightweight u2netp session
        from rembg import remove
        session = _get_rembg_session()

        # Run segmentation
        isolated_res = remove(
            cropped_pil,
            session=session,
            alpha_matting=False
        )

        if is_white_item:
            # Opacity guard for light/white garments
            alpha_channel = np.array(isolated_res.split()[-1])
            foreground_ratio = np.count_nonzero(alpha_channel > 25) / float(cw * ch)

            if foreground_ratio < 0.25:
                # Fallback to solid image if mask over-clipped the white garment
                final_pil = cropped_pil.convert("RGBA")
            else:
                final_pil = isolated_res
        else:
            final_pil = isolated_res

        buf_out = io.BytesIO()
        final_pil.save(buf_out, format="PNG", optimize=True)
        return buf_out.getvalue()

    except Exception as ex:
        print(f"[REMBG ISOLATION FALLBACK] {ex}", flush=True)
        if cropped_pil:
            fallback_buf = io.BytesIO()
            cropped_pil.save(fallback_buf, format="PNG")
            return fallback_buf.getvalue()
        return image_bytes

    finally:
        # Immediate memory cleanup
        for obj in [pil_img, cropped_pil, mask_img, final_pil]:
            if obj:
                try:
                    obj.close()
                except Exception:
                    pass
        gc.collect()


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
    pil_img.close()
    rotated_img.close()
    return buf_out.getvalue()