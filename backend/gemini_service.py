import os
import io
import json
import traceback
import re
from typing import List, Dict, Any, Optional
from PIL import Image, ImageOps
from google import genai
from google.genai import types

# Auto-repair malformed LLM JSON output
try:
    import json_repair
except ImportError:
    json_repair = None

# Support HEIC/HEIF formats from Apple devices
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# =====================================================================
# DYNAMIC TASK MODEL ROUTER (Aligned with AI Studio Quotas & Limits)
# =====================================================================
MODEL_ROUTER = {
    # 500 RPD / 15 RPM: High-throughput multimodal vision for bounding boxes & feature extraction
    "vision_ingest": os.getenv("MODEL_VISION_INGEST", "gemini-2.5-flash"),
    
    # High-reasoning model for wardrobe logic, harmony, and climate styling
    "styling_curator": os.getenv("MODEL_STYLING_CURATOR", "gemini-2.5-pro"),
    
    # Fast semantic deduplication
    "dedup_matcher": os.getenv("MODEL_DEDUP", "gemini-2.5-flash")
}


def _clean_json_text(raw_text: str) -> str:
    """Strips Markdown fences and extracts the raw JSON text body."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _ensure_rgb_jpeg_bytes(raw_bytes: bytes, max_dim: int = 1536) -> bytes:
    """
    Decodes raw photo bytes (HEIC/PNG/JPEG), applies EXIF orientation transpose,
    converts to RGB, and rescales to a clean JPEG buffer.
    """
    pil_img = Image.open(io.BytesIO(raw_bytes))

    # Correct iPhone orientation so bounding box coordinates remain aligned
    try:
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception:
        pass

    pil_img = pil_img.convert("RGB")
    w, h = pil_img.size

    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def compress_for_vision(raw_bytes: bytes, max_dim: int = 1024) -> bytes:
    """Public helper for image compression (used in lookbook and storage)."""
    return _ensure_rgb_jpeg_bytes(raw_bytes, max_dim=max_dim)


def detect_and_tag_garments(
    image_bytes: bytes = None,
    image_data: bytes = None,
    raw_bytes: bytes = None,
    user_gender: str = "women",
    **kwargs
) -> Dict[str, Any]:
    """
    Vision Ingestion Engine:
    Detects all visible garments and accessories in a photograph, returning bounding
    boxes [ymin, xmin, ymax, xmax] (0-1000 scale) and complete fashion metadata.
    """
    data = image_bytes or image_data or raw_bytes
    if not data:
        raise ValueError("No image bytes provided to detect_and_tag_garments.")

    if not client:
        raise RuntimeError("GEMINI_API_KEY is not configured in the environment.")

    # Prepare normalized JPEG image buffer
    jpeg_bytes = _ensure_rgb_jpeg_bytes(data, max_dim=1536)

    prompt = f"""
    You are an expert fashion cataloguer and computer vision analyst.
    Examine this photograph (which may be a multi-item flat-lay, single piece, wardrobe rack, or a person wearing an outfit).

    Target Tailoring Perspective: {user_gender}.

    Detect EVERY distinct wearable piece, garment, pair of shoes, or accessory (e.g. tops, blouses, knits, blazers, coats, trousers, jeans, skirts, dresses, sneakers, heels, boots, tote bags, handbags, sunglasses, jewelry, watches, belts, hats).

    For each item, output:
    1. "garment_type": Broad category strictly from: ["top", "bottom", "dress", "one_piece", "outerwear", "footwear", "accessory", "jewelry"]
    2. "sub_type": Specific item name (e.g. "Wide-Leg Jeans", "Ribbed Camisole Top", "Structured Tote Bag", "Oversized Wool Blazer", "Aviator Sunglasses")
    3. "primary_color": Dominant color name (e.g. "Light Blue", "Black", "Ivory White", "Oatmeal Beige", "Charcoal Grey")
    4. "secondary_colors": Array of secondary color names (e.g. ["Gold", "Silver"])
    5. "fabric_material": Identified material (e.g. "Denim", "Cotton Rib Knit", "Linen", "Calfskin Leather", "Merino Wool", "Silk", "Acetate")
    6. "pattern": Pattern type (e.g. "Solid", "Ribbed", "Pinstripe", "Floral", "Distressed")
    7. "formality": Integer rating from 1 (loungewear/ultra-casual) to 10 (black tie/formal gala)
    8. "seasons": Array of applicable seasons from: ["Spring", "Summer", "Autumn", "Winter", "All Season"]
    9. "style_tags": Array of aesthetic descriptors (e.g. ["minimalist", "casual", "tailored", "classic"])
    10. "dominant_color_hex": Approximate Hex color code (e.g. "#A0C4DF", "#1A1A1A")
    11. "box_2d": Bounding box coordinates normalized as [ymin, xmin, ymax, xmax] on a 0 to 1000 integer scale.

    Return ONLY a valid JSON object matching this schema:
    {{
      "items": [
        {{
          "garment_type": "bottom",
          "sub_type": "Wide-Leg Jeans",
          "primary_color": "Light Blue",
          "secondary_colors": [],
          "fabric_material": "Denim",
          "pattern": "Solid",
          "formality": 3,
          "seasons": ["Spring", "Summer", "Autumn", "All Season"],
          "style_tags": ["casual", "minimalist"],
          "dominant_color_hex": "#9BBAD4",
          "box_2d": [350, 180, 920, 810]
        }}
      ]
    }}
    """

    target_model = MODEL_ROUTER.get("vision_ingest", "gemini-2.5-flash")

    try:
        response = client.models.generate_content(
            model=target_model,
            contents=[
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )

        cleaned_text = _clean_json_text(response.text)

        parsed = None
        if json_repair:
            try:
                parsed = json_repair.loads(cleaned_text)
            except Exception:
                pass

        if parsed is None:
            parsed = json.loads(cleaned_text)

        if isinstance(parsed, dict) and "items" in parsed:
            return parsed
        elif isinstance(parsed, list):
            return {"items": parsed}
        return {"items": []}

    except Exception as e:
        print(f"\n--- GEMINI VISION INGESTION ERROR ({target_model}) ---")
        traceback.print_exc()
        print("------------------------------------------------------\n")
        raise RuntimeError(f"Gemini Vision error: {str(e)}")


def curate_outfit(
    user_id: str,
    user_gender: str,
    event_description: str,
    time_of_day: str,
    desired_vibe: str,
    weather: Dict[str, Any],
    available_items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Task: Multi-constraint Creative Styling & Cohesion Reasoning
    Routed to: MODEL_ROUTER["styling_curator"]
    """
    if not client:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    if not available_items:
        return {"error": "Closet catalog is empty."}

    manifest = []
    for it in available_items:
        manifest.append({
            "id": str(it.get("id") or it.get("db_id")),
            "garment_type": it.get("garment_type"),
            "sub_type": it.get("sub_type"),
            "primary_color": it.get("primary_color"),
            "fabric_material": it.get("fabric_material"),
            "pattern": it.get("pattern"),
            "formality": it.get("formality"),
            "seasons": it.get("seasons")
        })

    prompt = f"""
    You are an editorial personal stylist for an exclusive capsule wardrobe atelier.
    Curate the single best outfit from the client's available wardrobe pieces below.

    CLIENT CONTEXT:
    - Tailoring: {user_gender}
    - Occasion / Destination: {event_description}
    - Time of Day: {time_of_day}
    - Desired Aesthetic / Vibe: {desired_vibe}

    ATMOSPHERE & WEATHER:
    - Location: {weather.get('display_location', 'Local')}
    - Temperature: {weather.get('temperature_c', 20)}°C (Feels like: {weather.get('feels_like_c', 20)}°C)
    - Sky Condition: {weather.get('condition', 'Clear')}
    - Rain Status: {'Rain expected / wet' if weather.get('is_raining') else 'Dry conditions'}

    AVAILABLE WARDROBE PIECES:
    {json.dumps(manifest, indent=2)}

    STYLING RULES:
    1. Select ONLY item IDs that exist in the available wardrobe pieces manifest above.
    2. Build a complete, functional ensemble:
       - Either: [Top + Bottom] OR [Dress / One Piece]
       - Plus: Layering/Outerwear if weather demands it (<18°C or breezy/evening)
       - Plus: Footwear
       - Optional but encouraged: Accessory / Bag / Jewelry
    3. Ensure harmonious color coordination, fabric texture interplay, and appropriate formality balance.
    4. Provide an articulate, warm, and sophisticated styling rationale.

    Return ONLY a valid JSON object matching this schema:
    {{
      "outfit_name": "Evocative Title for the Look",
      "selected_item_ids": ["id1", "id2", "id3"],
      "styling_reasoning": "2-3 sentences explaining why these textures, cuts, and silhouettes work together for the occasion.",
      "weather_alignment": "1 sentence explaining why this outfit is comfortable for the forecast."
    }}
    """

    target_model = MODEL_ROUTER.get("styling_curator", "gemini-2.5-pro")

    try:
        response = client.models.generate_content(
            model=target_model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3
            )
        )
        cleaned_text = _clean_json_text(response.text)

        parsed = None
        if json_repair:
            try:
                parsed = json_repair.loads(cleaned_text)
            except Exception:
                pass

        if parsed is None:
            parsed = json.loads(cleaned_text)

        return parsed
    except Exception as e:
        print(f"\n--- GEMINI STYLING EXCEPTION ({target_model}) ---")
        traceback.print_exc()
        print("-------------------------------------------------\n")
        return {
            "outfit_name": "Classic Ensemble",
            "selected_item_ids": [m["id"] for m in manifest[:3]],
            "styling_reasoning": "Curated an essential combination from your available wardrobe.",
            "weather_alignment": "Well-balanced for the day."
        }


def find_potential_duplicate(new_item_desc: Dict[str, Any], existing_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Finds potential matching items in the closet and returns the existing item object.
    Distinguishes silhouette fits (e.g. 'Wide-Leg Jeans' vs 'Skinny Jeans').
    """
    new_cat = str(new_item_desc.get("garment_type", "")).lower().strip()
    new_sub = str(new_item_desc.get("sub_type", "")).lower().strip()
    new_color = str(new_item_desc.get("primary_color", "")).lower().strip()

    new_sub_words = set(re.findall(r'\w+', new_sub))
    new_color_words = set(re.findall(r'\w+', new_color))

    # Cut/fit distinctions that should NEVER automatically merge
    DISTINCT_FITS = [{"wide", "wide-leg", "baggy", "flare"}, {"skinny", "slim", "tight"}, {"straight", "classic"}]

    for existing in existing_items:
        ex_cat = str(existing.get("garment_type", "")).lower().strip()
        ex_sub = str(existing.get("sub_type", "")).lower().strip()
        ex_color = str(existing.get("primary_color", "")).lower().strip()

        if new_cat != ex_cat and not (new_cat in ["top", "dress"] and ex_cat in ["top", "dress"]):
            continue

        ex_color_words = set(re.findall(r'\w+', ex_color))
        color_match = bool(new_color_words & ex_color_words)
        if not color_match and new_color != ex_color:
            continue

        ex_sub_words = set(re.findall(r'\w+', ex_sub))

        # If both are jeans/pants but have conflicting fit types (e.g. wide-leg vs skinny), NOT a duplicate
        is_conflicting_fit = False
        for fit_set in DISTINCT_FITS:
            if bool(new_sub_words & fit_set) and not bool(ex_sub_words & fit_set) and any(bool(ex_sub_words & other_fit) for other_fit in DISTINCT_FITS if other_fit != fit_set):
                is_conflicting_fit = True
                break
        
        if is_conflicting_fit:
            continue

        # Check for word overlaps
        common_words = (new_sub_words & ex_sub_words) - {"top", "bottom", "piece", "garment", "light", "dark"}
        if len(common_words) >= 1:
            return existing

    return None


def format_taste_memory_prompt(taste_profile: Dict[str, Any]) -> str:
    """Formats dynamic Pillar 2 taste constraints for Gemini reasoning."""
    if not taste_profile:
        return "Taste Profile: Refined, effortless minimalist aesthetic."

    target_formality = taste_profile.get("target_formality", 4.5)
    fav_pairs = ", ".join(taste_profile.get("favorite_color_pairs", []))
    avoid_tags = ", ".join(taste_profile.get("avoided_tags", []))

    return f"""
    PERSONAL TASTE MEMORY & LEARNED CONSTRAINTS (Pillar 2 Dynamic Evolution):
    - Preferred Baseline Formality: ~{target_formality}/10 (balance relaxed comfort with intentional polish).
    - Learned Color Harmony Affinities: {fav_pairs or 'Neutral & soft earth tones'}.
    - Strongly Avoided Elements/Styles: {avoid_tags or 'Overly rigid corporate cuts, chaotic loud prints'}.
    - Weighting: Prioritize pieces with high tag weights ({taste_profile.get('tag_weights', {})}).
    """