import io
import cv2
import numpy as np
from PIL import Image, ImageOps
from rembg import remove, new_session

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# Lazy-loaded session cache to prevent heavy module loading at server startup
_REMBG_SESSION = None

def _get_rembg_session():
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        try:
            _REMBG_SESSION = new_session("u2net")
        except Exception:
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
    Precision cropping with balanced padding and solid alpha masking.
    Ensures white/cream/linen garments remain completely opaque.
    """
    pil_img = Image.open(io.BytesIO(image_bytes))
    try:
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception:
        pass

    pil_img = pil_img.convert("RGB")
    w, h = pil_img.size

    # box_2d is scaled 0 to 1000: [ymin, xmin, ymax, xmax]
    ymin, xmin, ymax, xmax = box_2d
    top = int((ymin / 1000.0) * h)
    left = int((xmin / 1000.0) * w)
    bottom = int((ymax / 1000.0) * h)
    right = int((xmax / 1000.0) * w)

    box_w = max(10, right - left)
    box_h = max(10, bottom - top)

    # Balanced padding to prevent chopping edges or over-zooming
    pad_ratio_x = 0.15 if not is_accessory else 0.25
    pad_ratio_y = 0.12 if not is_accessory else 0.20

    pad_x = int(box_w * pad_ratio_x)
    pad_y = int(box_h * pad_ratio_y)

    crop_top = max(0, top - pad_y)
    crop_left = max(0, left - pad_x)
    crop_bottom = min(h, bottom + pad_y)
    crop_right = min(w, right + pad_x)

    cropped_pil = pil_img.crop((crop_left, crop_top, crop_right, crop_bottom))
    cw, ch = cropped_pil.size
    orig_rgb = np.array(cropped_pil)

    # Resize buffer if image is excessively large for faster U2Net processing
    max_d = max(cw, ch)
    if max_d > 1024:
        scale = 1024.0 / float(max_d)
        proc_pil = cropped_pil.resize((int(cw * scale), int(ch * scale)), Image.Resampling.BILINEAR)
    else:
        proc_pil = cropped_pil

    buf_in = io.BytesIO()
    proc_pil.save(buf_in, format="PNG")
    cropped_bytes = buf_in.getvalue()

    is_white_item = any(
        w_name in primary_color.lower()
        for w_name in ["white", "ivory", "cream", "linen", "light", "beige", "oatmeal"]
    )

    try:
        session = _get_rembg_session()
        if session is not None:
            mask_bytes = remove(cropped_bytes, session=session, alpha_matting=False, only_mask=True)
        else:
            mask_bytes = remove(cropped_bytes, alpha_matting=False, only_mask=True)

        mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
        if mask_img.size != (cw, ch):
            mask_img = mask_img.resize((cw, ch), Image.Resampling.BILINEAR)

        mask_np = np.array(mask_img)
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

    except Exception:
        final_pil = cropped_pil

    buf_out = io.BytesIO()
    final_pil.save(buf_out, format="PNG", optimize=False)
    return buf_out.getvalue()


def rotate_image_bytes(image_bytes: bytes, degrees: int = 90) -> bytes:
    pil_img = Image.open(io.BytesIO(image_bytes))
    rotated_img = pil_img.rotate(-degrees, expand=True)
    buf_out = io.BytesIO()
    fmt = "PNG" if pil_img.mode == "RGBA" else "JPEG"
    rotated_img.save(buf_out, format=fmt)
    return buf_out.getvalue()