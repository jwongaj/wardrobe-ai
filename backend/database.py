import time
import os
import json
from typing import List, Dict, Any, Optional
from cloud_storage import resolve_image_url

try:
    from supabase import create_client, Client
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase: Optional[Client] = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None
except Exception:
    supabase = None

# Local memory fallback if Supabase credentials are not supplied
_LOCAL_CLOSET: List[Dict[str, Any]] = []
_LOCAL_LOOKS: List[Dict[str, Any]] = []
_LOCAL_TASTE: Dict[str, Dict[str, Any]] = {}

DEFAULT_ACTIVE_TAGS = [
    "Luminous Minimalist", "Relaxed Tailoring", "Neutral Earth Tones",
    "Breathable Linens", "Elevated Basics"
]
DEFAULT_SUGGESTED_TAGS = [
    "Quiet Luxury", "Soft Monochromatic", "Subtle Structure",
    "Warm Neutrals", "Casual Chic"
]
TAG_POOL = [
    "Quiet Luxury", "Soft Monochromatic", "Subtle Structure", "Warm Neutrals",
    "Casual Chic", "Airy Silhouettes", "Architectural Cuts", "Resort Elegance",
    "Earthy Minimalism", "Crisp Cotton", "Silk Accents", "Modern Classic",
    "Tailored Ease", "Neutral Linens", "Refined Monochrome", "Effortless Drapery"
]


# =========================================================================
# 1. CLOSET INVENTORY
# =========================================================================

def get_clothing_items_by_user(user_id: str) -> List[Dict[str, Any]]:
    items = []
    if supabase:
        try:
            res = supabase.table("clothing_items").select("*").eq("user_id", str(user_id)).execute()
            items = res.data or []
        except Exception as e:
            print(f"Supabase get_clothing_items error: {e}")
            items = []
    
    if not items:
        items = [item for item in _LOCAL_CLOSET if str(item.get("user_id")) == str(user_id)]

    # Auto-resolve relative image paths into loadable URLs/base64
    for itm in items:
        if itm.get("image_url"):
            itm["image_url"] = resolve_image_url(itm["image_url"])

    return items


def save_clothing_item(item: Dict[str, Any]) -> Dict[str, Any]:
    clean_item = dict(item)
    clean_item.pop("matched_existing", None)
    if "id" not in clean_item or not clean_item["id"]:
        clean_item["id"] = f"item_{int(time.time() * 1000)}"

    # Ensure image_url is stored cleanly
    if clean_item.get("image_url"):
        clean_item["image_url"] = resolve_image_url(clean_item["image_url"])

    if supabase:
        try:
            supabase.table("clothing_items").upsert(clean_item).execute()
            return clean_item
        except Exception as e:
            print(f"Supabase save_clothing_item error: {e}")

    _LOCAL_CLOSET.append(clean_item)
    return clean_item


def update_clothing_item_image(item_id: str, new_image_url: str) -> Optional[Dict[str, Any]]:
    resolved_url = resolve_image_url(new_image_url)
    if supabase:
        try:
            res = supabase.table("clothing_items").update({"image_url": resolved_url}).eq("id", str(item_id)).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            print(f"Supabase update_clothing_item_image error: {e}")

    for itm in _LOCAL_CLOSET:
        if str(itm.get("id")) == str(item_id) or str(itm.get("db_id")) == str(item_id):
            itm["image_url"] = resolved_url
            return itm
    return None


def delete_clothing_item(item_id: str) -> bool:
    if supabase:
        try:
            supabase.table("clothing_items").delete().eq("id", str(item_id)).execute()
            return True
        except Exception as e:
            print(f"Supabase delete_clothing_item error: {e}")

    global _LOCAL_CLOSET
    initial_len = len(_LOCAL_CLOSET)
    _LOCAL_CLOSET = [i for i in _LOCAL_CLOSET if str(i.get("id")) != str(item_id) and str(i.get("db_id")) != str(item_id)]
    return len(_LOCAL_CLOSET) < initial_len


# =========================================================================
# 2. PILLAR 2: TASTE MEMORY & ALGORITHM EVOLUTION
# =========================================================================

def get_user_taste_profile(user_id: str) -> Dict[str, Any]:
    clean_uid = str(user_id).strip()
    if supabase:
        try:
            res = supabase.table("user_taste_profiles").select("*").eq("user_id", clean_uid).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            print(f"Supabase get_user_taste_profile error: {e}")

    if clean_uid not in _LOCAL_TASTE:
        default_profile = {
            "user_id": clean_uid,
            "aesthetic_summary": "An effortless blend of luminous minimalism and relaxed tailoring with high affinity for neutral linens and subtle structure.",
            "target_formality": 4.5,
            "active_tags": list(DEFAULT_ACTIVE_TAGS),
            "suggested_tags": list(DEFAULT_SUGGESTED_TAGS),
            "avoided_tags": ["overly loud prints", "stiff corporate"],
            "tag_weights": {t.lower(): 1.2 for t in DEFAULT_ACTIVE_TAGS},
            "thumbs_up_count": 0,
            "thumbs_down_count": 0,
            "updated_at": int(time.time())
        }
        if supabase:
            try:
                supabase.table("user_taste_profiles").upsert(default_profile).execute()
            except Exception:
                pass
        _LOCAL_TASTE[clean_uid] = default_profile

    return _LOCAL_TASTE[clean_uid]


def save_user_feedback(
    user_id: str,
    rating: str,
    chips: List[str],
    outfit_items: List[Dict[str, Any]],
    outfit_id: Optional[str] = None
) -> Dict[str, Any]:
    profile = get_user_taste_profile(user_id)
    is_positive = (rating == "thumbs_up")

    if is_positive:
        profile["thumbs_up_count"] = profile.get("thumbs_up_count", 0) + 1
    else:
        profile["thumbs_down_count"] = profile.get("thumbs_down_count", 0) + 1

    formality_scores = [
        int(item.get("formality", 5))
        for item in outfit_items
        if "formality" in item and str(item.get("formality")).isdigit()
    ]
    if formality_scores:
        avg_form = sum(formality_scores) / len(formality_scores)
        if is_positive:
            profile["target_formality"] = round((float(profile.get("target_formality", 4.5)) * 0.7) + (avg_form * 0.3), 1)
        elif any("formal" in c.lower() for c in chips):
            profile["target_formality"] = max(1.0, round(float(profile.get("target_formality", 4.5)) - 0.5, 1))
        elif any("casual" in c.lower() for c in chips):
            profile["target_formality"] = min(10.0, round(float(profile.get("target_formality", 4.5)) + 0.5, 1))

    multiplier = 1.20 if is_positive else 0.75
    tag_weights = profile.get("tag_weights", {})
    for item in outfit_items:
        extracted = list(item.get("style_tags", []))
        if item.get("fabric_material"):
            extracted.append(str(item.get("fabric_material")))
        if item.get("primary_color"):
            extracted.append(str(item.get("primary_color")))

        for tag in extracted:
            k = str(tag).lower().strip()
            if k:
                tag_weights[k] = round(max(0.2, min(tag_weights.get(k, 1.0) * multiplier, 3.0)), 2)

    profile["tag_weights"] = tag_weights
    profile["updated_at"] = int(time.time())

    if supabase:
        try:
            supabase.table("user_taste_profiles").upsert(profile).execute()
        except Exception as e:
            print(f"Supabase save_user_feedback error: {e}")

    _LOCAL_TASTE[str(user_id)] = profile
    return profile


def save_taste_tags(
    user_id: str,
    active_tags: List[str],
    avoided_tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    profile = get_user_taste_profile(user_id)
    profile["active_tags"] = active_tags
    if avoided_tags is not None:
        profile["avoided_tags"] = avoided_tags

    tag_weights = profile.get("tag_weights", {})
    for t in active_tags:
        tag_weights[t.lower()] = max(tag_weights.get(t.lower(), 1.0), 1.3)
    profile["tag_weights"] = tag_weights
    profile["suggested_tags"] = [tag for tag in TAG_POOL if tag not in active_tags][:5]

    if active_tags:
        profile["aesthetic_summary"] = f"A signature curation centered around {', '.join(active_tags)}, calibrated for an effortless and polished everyday presence."
    else:
        profile["aesthetic_summary"] = "An effortless blend of versatile essentials and neutral foundations."

    profile["updated_at"] = int(time.time())

    if supabase:
        try:
            supabase.table("user_taste_profiles").upsert(profile).execute()
        except Exception as e:
            print(f"Supabase save_taste_tags error: {e}")

    _LOCAL_TASTE[str(user_id)] = profile
    return profile


# =========================================================================
# 3. LOOKBOOK PERSISTENCE & AUTO-HYDRATION
# =========================================================================

def get_saved_outfits_by_user(user_id: str) -> List[Dict[str, Any]]:
    looks = []
    if supabase:
        try:
            res = supabase.table("saved_outfits").select("*").eq("user_id", str(user_id)).execute()
            looks = res.data or []
        except Exception as e:
            print(f"Supabase get_saved_outfits error: {e}")
    
    if not looks:
        looks = [look for look in _LOCAL_LOOKS if str(look.get("user_id")) == str(user_id)]

    # Fetch closet items to auto-hydrate legacy records with missing item payloads
    closet_items = get_clothing_items_by_user(user_id)
    closet_map = {str(it.get("id")): it for it in closet_items}
    for it in closet_items:
        if it.get("db_id"):
            closet_map[str(it.get("db_id"))] = it

    for look in looks:
        # Resolve legacy item_ids into full items objects
        items_payload = look.get("items")
        if isinstance(items_payload, str):
            try:
                items_payload = json.loads(items_payload)
            except Exception:
                items_payload = []

        if not items_payload and look.get("item_ids"):
            item_ids = look["item_ids"]
            if isinstance(item_ids, str):
                try:
                    item_ids = json.loads(item_ids)
                except Exception:
                    item_ids = []
            items_payload = [closet_map[str(iid)] for iid in item_ids if str(iid) in closet_map]

        # Resolve image URLs inside garments
        if items_payload:
            for itm in items_payload:
                if itm.get("image_url"):
                    itm["image_url"] = resolve_image_url(itm["image_url"])
            look["items"] = items_payload

        # Resolve look top-level image
        if look.get("image_url"):
            look["image_url"] = resolve_image_url(look["image_url"])
        elif items_payload and items_payload[0].get("image_url"):
            look["image_url"] = items_payload[0]["image_url"]

    return looks


def save_outfit_record(look_payload: Dict[str, Any]) -> Dict[str, Any]:
    clean_look = dict(look_payload)
    if "id" not in clean_look or not clean_look["id"]:
        clean_look["id"] = f"look_{int(time.time() * 1000)}"
    if "created_at" not in clean_look or not clean_look["created_at"]:
        clean_look["created_at"] = time.strftime("%Y-%m-%d %H:%M")

    # Clean title from emojis
    if "title" in clean_look:
        clean_look["title"] = clean_look["title"].replace("🥂", "").replace("✨", "").strip()

    # Resolve image URLs before writing
    if clean_look.get("image_url"):
        clean_look["image_url"] = resolve_image_url(clean_look["image_url"])

    if supabase:
        try:
            supabase.table("saved_outfits").upsert(clean_look).execute()
            return clean_look
        except Exception as e:
            print(f"Supabase save_outfit_record error: {e}")

    _LOCAL_LOOKS.append(clean_look)
    return clean_look


def delete_saved_outfit_record(look_id: str) -> bool:
    if supabase:
        try:
            supabase.table("saved_outfits").delete().eq("id", str(look_id)).execute()
            return True
        except Exception as e:
            print(f"Supabase delete_saved_outfit_record error: {e}")

    global _LOCAL_LOOKS
    init_len = len(_LOCAL_LOOKS)
    _LOCAL_LOOKS = [l for l in _LOCAL_LOOKS if str(l.get("id")) != str(look_id)]
    return len(_LOCAL_LOOKS) < init_len