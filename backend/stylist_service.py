import json
from typing import Dict, Any, List, Optional
from google import genai
from model_router import STYLIST_CASCADE, generate_with_fallback


def generate_fallback_outfit(
    items: List[Dict[str, Any]],
    temp_c: float,
    target_formality: float = 4.5,
    avoid_ids: Optional[List[Any]] = None
) -> Dict[str, Any]:
    avoid_set = {str(i) for i in (avoid_ids or [])}

    def formality_diff(it):
        return abs(float(it.get("formality", 5)) - target_formality)

    available_items = [
        it for it in items 
        if str(it.get("id") or it.get("db_id")) not in avoid_set
    ] or items

    tops = sorted(
        [it for it in available_items if str(it.get("garment_type", "")).lower() in ["top", "shirt", "blouse", "knitwear", "t-shirt"]],
        key=formality_diff
    )
    bottoms = sorted(
        [it for it in available_items if str(it.get("garment_type", "")).lower() in ["bottom", "trousers", "pants", "skirt", "jeans", "shorts"]],
        key=formality_diff
    )
    dresses = sorted(
        [it for it in available_items if str(it.get("garment_type", "")).lower() in ["dress", "one-piece", "one_piece", "jumpsuit"]],
        key=formality_diff
    )
    outerwear = sorted(
        [it for it in available_items if str(it.get("garment_type", "")).lower() in ["outerwear", "jacket", "coat", "blazer"]],
        key=formality_diff
    )

    selected_ids = []
    if dresses:
        selected_ids.append(dresses[0].get("id") or dresses[0].get("db_id"))
    elif tops and bottoms:
        selected_ids.append(tops[0].get("id") or tops[0].get("db_id"))
        selected_ids.append(bottoms[0].get("id") or bottoms[0].get("db_id"))
    elif available_items:
        selected_ids = [available_items[0].get("id") or available_items[0].get("db_id")]

    if temp_c <= 16.0 and outerwear:
        selected_ids.append(outerwear[0].get("id") or outerwear[0].get("db_id"))

    return {
        "outfit_name": "Harmonious Day Capsule",
        "styling_reasoning": "A balanced ensemble matching silhouette volume and formality across layers.",
        "weather_alignment": f"Selected core layers suited for {temp_c}°C ambient conditions.",
        "selected_item_ids": [i for i in selected_ids if i is not None]
    }


async def generate_outfit_recommendation(
    client: genai.Client,
    user_gender: str,
    event_description: str,
    time_of_day: str,
    desired_vibe: str,
    weather: Dict[str, Any],
    items: List[Dict[str, Any]],
    taste_profile: Optional[Dict[str, Any]] = None,
    disliked_combinations: Optional[List[List[Any]]] = None
) -> Dict[str, Any]:
    # 1. Structure clear garment metadata
    catalog_summary = []
    for it in items:
        item_id = str(it.get("id") or it.get("db_id"))
        catalog_summary.append({
            "id": item_id,
            "type": it.get("garment_type", "garment"),
            "sub": it.get("sub_type", "item"),
            "color": it.get("primary_color", "neutral"),
            "mat": it.get("fabric_material", "natural"),
            "form": it.get("formality", 5),
            "vibe": it.get("style_tags", [])
        })

    location = weather.get("display_location") or weather.get("city", "Local")
    temp_c = weather.get("temp_c") or weather.get("temperature_c", 20.0)
    feels_like = weather.get("feels_like_c", temp_c)
    condition = weather.get("condition", "Mild")
    is_rain = weather.get("is_raining", False)

    taste = taste_profile or {}
    active_tags = ", ".join(taste.get("active_tags", ["Luminous Minimalist"]))

    # 2. Strict Negative Constraint Formatting
    banned_instructions = ""
    flattened_avoid_ids = []
    if disliked_combinations:
        disliked_str_list = []
        for combo in disliked_combinations:
            clean_combo = [str(x) for x in combo]
            disliked_str_list.append(str(clean_combo))
            flattened_avoid_ids.extend(clean_combo)

        banned_instructions = f"""
STRICT NEGATIVE CONSTRAINTS (USER REJECTED PAIRINGS):
The user thumbed down these exact item combinations:
{chr(10).join(disliked_str_list)}

ANTI-LAZY-PIVOT RULES:
1. You MUST NOT reuse the exact same core foundation (do not keep the same top+bottom or dress while just adding an accessory).
2. You MUST swap at least one major garment piece (top, bottom, or dress).
"""

    # 3. Formality & Coherence Stylist Prompt
    prompt = f"""
You are an editorial wardrobe stylist and luxury capsule curator.

CONTEXT:
- Occasion / Destination: {event_description}
- Time of Day: {time_of_day}
- Requested Vibe / Mood: "{desired_vibe}"
- Climate: {location} | {temp_c}°C (feels {feels_like}°C), {condition}, Rain: {is_rain}
- User Style Profile: {active_tags}

{banned_instructions}

WARDROBE INVENTORY:
{json.dumps(catalog_summary, separators=(',', ':'))}

CRITICAL STYLING PRINCIPLES (MUST FOLLOW STRICTLY):
1. **FORMALITY HARMONY (NO VIBE CLASHES):**
   - Garments and footwear MUST share a compatible formality score (within $\\pm 2$ on the 1-10 scale).
   - NEVER pair casual daytime pieces (e.g., casual sundresses, linen shirts, denim, jersey tees) with formal evening footwear (e.g., stiletto heels, patent leather dress shoes, satin pumps).
   - Casual pieces belong with relaxed footwear (e.g., clean trainers, minimalist leather slides, flat sandals, canvas sneakers).
   - Formal pieces belong with tailored or elevated footwear.
   - Matching color alone is NOT enough — texture, structure, and aesthetic level MUST harmonize.

2. **VIBE FIDELITY:**
   - If the user requests "{desired_vibe}", let this dictate the energy, colors, and cut of the outfit.
   - If "{desired_vibe}" includes words like 'colorful', 'bold', or 'vibrant', pick colorful pieces rather than defaulting to monochrome/all-white.

3. **STRUCTURAL COMPLETENESS:**
   - Build a complete look: [Top + Bottom OR Dress] + optional [Outerwear if {temp_c}°C warrants] + optional [Footwear / Bag / Accessory].
   - Ensure fabrics complement each other (e.g., linen with cotton/canvas, crisp tailoring with fine knitwear or silk).

Return ONLY a valid JSON object matching this schema:
{{
  "outfit_name": "Editorial Look Title",
  "styling_reasoning": "2 sentences explaining the texture harmony, formality balance, and why this look embodies '{desired_vibe}'.",
  "weather_alignment": "1 sentence on climate comfort for {temp_c}°C.",
  "selected_item_ids": ["id1", "id2"]
}}
"""

    result = generate_with_fallback(
        client=client,
        model_cascade=STYLIST_CASCADE,
        prompt=prompt,
        max_output_tokens=500
    )

    if result["success"] and result["data"]:
        data = result["data"]
        if "selected_item_ids" in data:
            data["selected_item_ids"] = [str(i) for i in data["selected_item_ids"] if i is not None]
        data["_model_used"] = result["model_used"]
        return data

    return generate_fallback_outfit(
        items,
        temp_c,
        avoid_ids=flattened_avoid_ids
    )