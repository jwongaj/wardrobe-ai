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
    """
    Deterministic rule-based wardrobe builder when LLM quotas are exhausted.
    Sorts items by formality proximity while skipping avoided/rejected IDs.
    """
    avoid_set = set(str(i) for i in (avoid_ids or []))

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
        "outfit_name": "Classic Balanced Capsule (Rule-Based Mode)",
        "styling_reasoning": "A clean, functional pairing constructed from your wardrobe essentials while AI services are refreshing.",
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
    """
    Curates a personalized ensemble using Gemini with dynamic Pillar 2 taste memory
    and negative constraints to prevent duplicate recommendations.
    """
    # 1. Compact payload to minimize input tokens
    catalog_summary = []
    for it in items:
        item_id = it.get("id") or it.get("db_id")
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

    # 2. Extract Pillar 2 Dynamic Taste Signals
    taste = taste_profile or {}
    target_formality = taste.get("target_formality", 4.5)
    active_tags = ", ".join(taste.get("active_tags", ["Luminous Minimalist", "Relaxed Tailoring"]))
    avoided_tags = ", ".join(taste.get("avoided_tags", ["overly loud prints", "stiff corporate"]))
    aesthetic_summary = taste.get("aesthetic_summary", "Clean, intentional styling with relaxed proportions.")

    # 3. Build Negative Constraints from Disliked Outfits
    dislike_clause = ""
    flattened_disliked_ids = []
    if disliked_combinations:
        formatted_combos = [f"Combination #{i+1}: {c}" for i, c in enumerate(disliked_combinations)]
        dislike_clause = f"""
STRICT NEGATIVE CONSTRAINTS (PREVIOUSLY REJECTED / DISLIKED):
- The user has actively thumbed-down and rejected these exact item pairings:
  {chr(10).join(formatted_combos)}
- CRITICAL: You MUST NOT return the same grouping or core pairing. Suggest an alternative, fresh curation.
"""
        for combo in disliked_combinations:
            flattened_disliked_ids.extend(combo)

    # 4. Construct Reasoning Prompt with Memory Loop
    prompt = f"""
You are an expert luxury capsule wardrobe stylist and personal taste curator.

CLIENT CONTEXT:
- Silhouette Preference: {user_gender}
- Occasion / Venue: {event_description}
- Time of Day: {time_of_day}
- Target Vibe: {desired_vibe}
- Climate: {location} | {temp_c}°C (feels {feels_like}°C), {condition}, Rain: {is_rain}

PILLAR 2 TASTE MEMORY & LEARNED CONSTRAINTS:
- Aesthetic Identity: "{aesthetic_summary}"
- Learned Formality Baseline: ~{target_formality}/10 (balance ease and intentional structure).
- Active Aesthetic Labels: {active_tags}.
- Strictly Avoided Styles: {avoided_tags}.
- High Affinity: Prioritize pieces whose fabrics, cuts, and colors align with the active labels.
{dislike_clause}
WARDROBE ITEMS (Select strictly from this list):
{json.dumps(catalog_summary, separators=(',', ':'))}

CURATION RULES:
1. Select complementary items strictly from the provided list.
2. Build a complete look: [Top + Bottom OR Dress] + optional [Outerwear if {temp_c}°C warrants] + optional [Footwear / Accessories].
3. Ensure pieces harmonize in silhouette volume, formality balance, and tonal palette.
4. If a previously rejected combo is present above, pivot to an alternative combination of tops/bottoms/dresses.

Return ONLY a valid JSON object matching this schema:
{{
  "outfit_name": "Editorial look title",
  "styling_reasoning": "2 sentences explaining the texture harmony, silhouette balance, and why this fits the occasion and learned taste.",
  "weather_alignment": "1 sentence on thermal comfort and weather suitability for {temp_c}°C in {location}.",
  "selected_item_ids": ["id1", "id2"]
}}
"""

    # Run through dynamic model cascade
    result = generate_with_fallback(
        client=client,
        model_cascade=STYLIST_CASCADE,
        prompt=prompt,
        max_output_tokens=500
    )

    if result["success"] and result["data"]:
        data = result["data"]
        if "selected_item_ids" in data:
            data["selected_item_ids"] = [i for i in data["selected_item_ids"] if i is not None]
        data["_model_used"] = result["model_used"]
        return data

    print(f"[Stylist] All AI cascade models exhausted ({result.get('error')}). Using deterministic engine.")
    return generate_fallback_outfit(
        items,
        temp_c,
        target_formality=target_formality,
        avoid_ids=flattened_disliked_ids
    )