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
        "outfit_name": "Fresh Alternative Capsule",
        "styling_reasoning": "A clean rotation styled from your alternative wardrobe pieces.",
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
    # 1. Compact catalog representation
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

    # 2. Strict Negative Constraint Formatting with Anti-Lazy-Pivot Rules
    banned_instructions = ""
    flattened_avoid_ids = []
    if disliked_combinations:
        disliked_str_list = []
        for combo in disliked_combinations:
            clean_combo = [str(x) for x in combo]
            disliked_str_list.append(str(clean_combo))
            flattened_avoid_ids.extend(clean_combo)

        banned_instructions = f"""
CRITICAL NEGATIVE CONSTRAINTS (USER REJECTED THESE EXACT COMBINATIONS):
The user explicitly thumbed down and rejected these previous item pairings:
{chr(10).join(disliked_str_list)}

ANTI-LAZY-PIVOT RULES (STRICT COMPLIANCE REQUIRED):
1. You MUST NOT retain the exact same core clothing foundation (do NOT keep the same top + bottom or dress and simply add/change a necklace, jewelry, shoes, or accessory).
2. You MUST replace at least one primary anchor garment (choose a distinctly different top, bottom, or dress).
3. If the user previously disliked a look, pivot the overall silhouette and color balance noticeably.
"""

    # 3. Dynamic Prompt with High Priority on User's Immediate Vibe
    prompt = f"""
You are an expert personal wardrobe stylist and luxury capsule curator.

IMMEDIATE REQUEST PRIORITY (MUST FOLLOW ABOVE ALL ELSE):
- Target Vibe / Mood: "{desired_vibe}" (CRITICAL: If the user requests "{desired_vibe}", prioritize items with colors, cuts, and aesthetics that actively embody "{desired_vibe}". Do NOT default to neutral or all-white unless explicitly requested).
- Occasion / Destination: {event_description}
- Time of Day: {time_of_day}
- Weather: {location} | {temp_c}°C (feels {feels_like}°C), {condition}, Rain: {is_rain}

LONG-TERM TASTE SIGNALS:
- Baseline Taste: {active_tags}

{banned_instructions}

AVAILABLE WARDROBE PIECES:
{json.dumps(catalog_summary, separators=(',', ':'))}

CURATION RULES:
1. Return items strictly from the list above using their exact "id".
2. Build a complete look: (Top + Bottom) OR (Dress) + optional Outerwear/Shoes/Accessories.
3. Strongly reflect the requested vibe "{desired_vibe}" across color harmony and garment silhouette.

Return ONLY a JSON object matching this schema:
{{
  "outfit_name": "Descriptive Look Title",
  "styling_reasoning": "2 sentences explaining why this look embodies '{desired_vibe}' and harmonizes with the occasion.",
  "weather_alignment": "1 sentence on climate comfort.",
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