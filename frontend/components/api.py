import os
import httpx
import streamlit as st
from typing import List, Dict, Any, Optional

# Default to your live Render backend
API_BASE_URL = os.getenv("API_BASE_URL", "https://wardrobe-ai-backend-7gil.onrender.com").rstrip("/")
CLIENT_TIMEOUT = 120.0


def check_health() -> bool:
    try:
        with httpx.Client(timeout=4.0) as client:
            res = client.get(f"{API_BASE_URL}/")
            return res.status_code == 200
    except Exception:
        return False


def ingest_image(file, user_id: str, user_gender: str) -> Dict[str, Any]:
    try:
        file_bytes = file.getvalue() if hasattr(file, "getvalue") else file.read()
        file_name = getattr(file, "name", "upload.jpg")
        mime_type = getattr(file, "type", "image/jpeg") or "image/jpeg"

        files = {"file": (file_name, file_bytes, mime_type)}
        data = {"user_id": user_id, "user_gender": user_gender}

        with httpx.Client(timeout=CLIENT_TIMEOUT) as client:
            res = client.post(f"{API_BASE_URL}/api/v1/wardrobe/ingest", files=files, data=data)
            if res.status_code == 200:
                st.cache_data.clear()
                return res.json()
            return {"status": "error", "error": f"HTTP {res.status_code}: {res.text}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def save_single_item(item_payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        clean_payload = {k: v for k, v in item_payload.items() if k != "matched_existing"}
        with httpx.Client(timeout=20.0) as client:
            res = client.post(f"{API_BASE_URL}/api/v1/wardrobe/item", json=clean_payload)
            if res.status_code == 200:
                st.cache_data.clear()
                return res.json()
            return {"status": "error", "error": res.text}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def update_item_image(item_id: str, image_url: str) -> Dict[str, Any]:
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.put(f"{API_BASE_URL}/api/v1/wardrobe/items/{item_id}/image", json={"image_url": image_url})
            if res.status_code == 200:
                st.cache_data.clear()
                return res.json()
            return {"status": "error", "error": res.text}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@st.cache_data(ttl=30, show_spinner=False)
def get_clothing_items(user_id: str) -> List[Dict[str, Any]]:
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(f"{API_BASE_URL}/api/v1/wardrobe/items", params={"user_id": user_id})
            if res.status_code == 200:
                return res.json()
            return []
    except Exception:
        return []


def delete_clothing_item(item_id: str) -> bool:
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.delete(f"{API_BASE_URL}/api/v1/wardrobe/items/{item_id}")
            if res.status_code == 200:
                st.cache_data.clear()
                return True
            return False
    except Exception:
        return False


def get_taste_profile(user_id: str) -> Dict[str, Any]:
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(f"{API_BASE_URL}/api/v1/taste/profile", params={"user_id": user_id})
            if res.status_code == 200:
                data = res.json()
                return data.get("profile", data) if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def submit_binary_feedback(user_id: str, rating: str, chips: List[str], outfit_items: Optional[List[Dict[str, Any]]] = None, outfit_id: Optional[str] = None) -> Dict[str, Any]:
    payload = {"user_id": user_id, "outfit_id": outfit_id, "rating": rating, "chips": chips, "outfit_items": outfit_items or []}
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.post(f"{API_BASE_URL}/api/v1/taste/feedback", json=payload)
            return res.json() if res.status_code == 200 else {"status": "error"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def update_taste_tags(user_id: str, active_tags: List[str], avoided_tags: Optional[List[str]] = None) -> Dict[str, Any]:
    payload = {"user_id": user_id, "active_tags": active_tags, "avoided_tags": avoided_tags}
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.post(f"{API_BASE_URL}/api/v1/taste/profile/tags", json=payload)
            return res.json().get("profile", {}) if res.status_code == 200 else {}
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=120, show_spinner=False)
def fetch_weather(location: Optional[str] = None) -> Dict[str, Any]:
    params = {"location": location} if location else {}
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(f"{API_BASE_URL}/api/v1/weather", params=params)
            if res.status_code == 200:
                return res.json()
    except Exception:
        pass
    return {"city": "Local", "display_location": "Local", "temperature_c": 21.0, "feels_like_c": 21.0, "condition": "Clear & Pleasant", "is_raining": False}


def curate_outfit(user_id: str, user_gender: str, event_description: str, time_of_day: str, desired_vibe: str, weather: Dict[str, Any], available_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload = {"user_id": user_id, "user_gender": user_gender, "event_description": event_description, "time_of_day": time_of_day, "desired_vibe": desired_vibe, "weather": weather, "available_items": available_items}
    try:
        with httpx.Client(timeout=45.0) as client:
            res = client.post(f"{API_BASE_URL}/api/v1/outfits/generate", json=payload)
            return res.json() if res.status_code == 200 else {"error": res.text}
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=30, show_spinner=False)
def get_saved_outfits(user_id: str) -> List[Dict[str, Any]]:
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(f"{API_BASE_URL}/api/v1/outfits/saved", params={"user_id": user_id})
            if res.status_code == 200:
                return res.json()
    except Exception:
        pass
    return []


def save_look(payload: Dict[str, Any]) -> bool:
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.post(f"{API_BASE_URL}/api/v1/outfits/save", json=payload)
            if res.status_code == 200:
                st.cache_data.clear()
                return True
            return False
    except Exception:
        return False


def delete_saved_outfit(outfit_id: Any) -> bool:
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.delete(f"{API_BASE_URL}/api/v1/outfits/saved/{outfit_id}")
            if res.status_code == 200:
                st.cache_data.clear()
                return True
            return False
    except Exception:
        return False


def purge_unlinked_storage() -> Dict[str, Any]:
    """Safe fallback helper for admin storage purge."""
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.post(f"{API_BASE_URL}/api/v1/admin/purge-storage")
            if res.status_code == 200:
                return res.json()
    except Exception:
        pass
    return {"success": True, "count": 0}