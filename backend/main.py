import sys
from pathlib import Path

# Add backend directory to Python sys.path automatically
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import time
import httpx
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request, Body
from fastapi.middleware.cors import CORSMiddleware

# Configurations & Local Services
from config import genai_client
import database
import cloud_storage
import stylist_service
import image_processor
import gemini_service
import weather_service
from schemas import (
    OutfitRequest,
    IngestionResponse,
    SavedOutfitCreate,
    BinaryFeedbackPayload,
    UpdateTasteTagsPayload,
    TasteProfileResponse
)

import os
import uvicorn

# Initialize database schema/store if applicable
if hasattr(database, "init_db"):
    database.init_db()

app = FastAPI(
    title="WoLo Wardrobe API",
    version="1.2.0",
    description="Multi-tenant digital wardrobe archive, dynamic taste memory, and AI styling salon backend."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "online", "service": "WoLo Wardrobe Backend", "timestamp": int(time.time())}


# =========================================================================
# PILLAR 1: WARDROBE CATALOG & INGESTION
# =========================================================================

@app.get("/api/v1/wardrobe/items")
async def get_wardrobe_items(user_id: str = Query(..., description="ID of the active user")):
    """Fetches all cataloged garments for a specific user."""
    try:
        return database.get_clothing_items_by_user(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/wardrobe/items/{item_id}")
async def get_wardrobe_item_by_id(item_id: str):
    """Fetches details for a single garment."""
    if hasattr(database, "get_clothing_item_by_id"):
        item = database.get_clothing_item_by_id(item_id)
        if item:
            return item
    items = database.CLOSET_STORE if hasattr(database, "CLOSET_STORE") else []
    for itm in items:
        if str(itm.get("id")) == str(item_id) or str(itm.get("db_id")) == str(item_id):
            return itm
    raise HTTPException(status_code=404, detail=f"Garment #{item_id} not found.")


@app.post("/api/v1/wardrobe/ingest")
async def ingest_wardrobe_image(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    user_gender: str = Form("women")
):
    try:
        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        detection_result = gemini_service.detect_and_tag_garments(
            image_bytes=raw_bytes,
            user_gender=user_gender
        )

        detected_items = detection_result.get("items", [])
        if not detected_items:
            raise HTTPException(status_code=422, detail="No garments or accessories detected.")

        existing_items = database.get_clothing_items_by_user(user_id)
        processed_records = []
        pending_duplicates = []
        timestamp = int(time.time())

        for idx, item in enumerate(detected_items):
            box_2d = item.get("box_2d")
            if not box_2d or len(box_2d) != 4:
                continue

            garment_type = str(item.get("garment_type", "top")).lower()
            sub_type = str(item.get("sub_type", "Garment")).strip()
            primary_color = str(item.get("primary_color", "Neutral")).strip()

            is_acc = any(k in garment_type or k in sub_type.lower() for k in [
                "accessory", "jewelry", "eyewear", "glasses", "sunglasses",
                "sunnies", "bag", "tote", "shoe", "footwear", "watch", "belt", "hat"
            ])

            isolated_png_bytes = image_processor.crop_and_isolate_garment(
                image_bytes=raw_bytes,
                box_2d=box_2d,
                garment_type=garment_type,
                primary_color=primary_color,
                is_accessory=is_acc
            )

            filename = f"items/{user_id}_{timestamp}_{idx}.png"
            image_url = cloud_storage.upload_image_bytes(
                image_bytes=isolated_png_bytes,
                destination_path=filename,
                mime_type="image/png"
            )

            item_payload = {
                "user_id": user_id,
                "garment_type": item.get("garment_type", "top"),
                "sub_type": sub_type,
                "primary_color": primary_color,
                "secondary_colors": item.get("secondary_colors", []),
                "pattern": item.get("pattern", "Solid"),
                "fabric_material": item.get("fabric_material", "Fabric"),
                "formality": int(item.get("formality", 5)),
                "seasons": item.get("seasons", ["Spring", "Summer", "Autumn"]),
                "style_tags": item.get("style_tags", ["minimalist"]),
                "dominant_color_hex": item.get("dominant_color_hex", "#CCCCCC"),
                "image_url": image_url
            }

            matched_dup = gemini_service.find_potential_duplicate(item, existing_items)
            if matched_dup:
                item_payload["matched_existing"] = matched_dup
                pending_duplicates.append(item_payload)
            else:
                saved = database.save_clothing_item(item_payload)
                processed_records.append(saved)

        return {
            "status": "success",
            "detected_count": len(detected_items),
            "ingested_count": len(processed_records),
            "items": processed_records,
            "pending_duplicates": pending_duplicates
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/wardrobe/item")
async def save_single_wardrobe_item(item: Dict[str, Any] = Body(...)):
    """Saves a single approved item to the user's database."""
    item.pop("matched_existing", None)
    saved = database.save_clothing_item(item)
    return {"status": "success", "item": saved}


@app.put("/api/v1/wardrobe/items/{item_id}/image")
async def update_item_image_url(item_id: str, payload: Dict[str, str] = Body(...)):
    """Replaces an existing item's image URL."""
    new_url = payload.get("image_url")
    updated = database.update_clothing_item_image(item_id, new_url)
    return {"status": "success", "item": updated}


@app.post("/api/v1/wardrobe/items/{item_id}/rotate")
async def rotate_wardrobe_item(item_id: str, degrees: int = 90):
    """Rotates an existing garment image and updates storage."""
    items = database.get_clothing_items_by_user("") if not hasattr(database, "CLOSET_STORE") else database.CLOSET_STORE
    target_item = None
    for itm in items:
        if str(itm.get("id")) == str(item_id) or str(itm.get("db_id")) == str(item_id):
            target_item = itm
            break

    if not target_item or not target_item.get("image_url"):
        raise HTTPException(status_code=404, detail="Item or image not found.")

    image_url = target_item["image_url"]

    # If inline base64 data URI
    if image_url.startswith("data:"):
        import base64
        header, b64data = image_url.split(",", 1)
        raw_img_bytes = base64.b64decode(b64data)
        rotated_bytes = image_processor.rotate_image_bytes(raw_img_bytes, degrees=degrees)
        new_url = cloud_storage.upload_image_bytes(rotated_bytes, f"rotated_{item_id}.png", "image/png")
    else:
        clean_url = image_url.split("?")[0]
        async with httpx.AsyncClient(timeout=30.0) as client:
            img_res = await client.get(clean_url)
            if img_res.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch image.")
        rotated_bytes = image_processor.rotate_image_bytes(img_res.content, degrees=degrees)
        new_url = cloud_storage.upload_image_bytes(rotated_bytes, f"rotated_{item_id}.png", "image/png")

    database.update_clothing_item_image(item_id, new_url)
    return {"status": "success", "new_image_url": new_url}


@app.delete("/api/v1/wardrobe/items/{item_id}")
async def delete_wardrobe_item(item_id: str):
    """Deletes a garment from the database and storage."""
    deleted = database.delete_clothing_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Garment #{item_id} not found.")
    return {"status": "success", "deleted_id": item_id}


# =========================================================================
# PILLAR 2: TASTE MEMORY & "YOUR ALGORITHM" ENGINE
# =========================================================================

@app.get("/api/v1/taste/profile")
async def get_taste_profile_route(user_id: str = Query(..., description="Active user ID")):
    """Fetches the user's dynamic taste profile, active tags, and 1-sentence aesthetic summary."""
    profile = database.get_user_taste_profile(user_id)
    return {"status": "success", "profile": profile}


@app.post("/api/v1/taste/feedback")
async def submit_outfit_feedback(payload: BinaryFeedbackPayload):
    """Processes binary 👍/👎 feedback + tags and adjusts dynamic taste weights."""
    try:
        updated_profile = database.save_user_feedback(
            user_id=payload.user_id,
            rating=payload.rating,
            chips=payload.chips,
            outfit_items=payload.outfit_items or [],
            outfit_id=payload.outfit_id
        )
        return {"status": "success", "profile": updated_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/taste/profile/tags")
async def update_taste_tags_route(payload: UpdateTasteTagsPayload):
    """Updates active algorithm tags and regenerates the 1-sentence aesthetic summary."""
    try:
        updated_profile = database.save_taste_tags(
            user_id=payload.user_id,
            active_tags=payload.active_tags,
            avoided_tags=payload.avoided_tags
        )
        return {"status": "success", "profile": updated_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# PILLAR 3: OUTFIT STYLIST & REASONING
# =========================================================================

@app.post("/api/v1/outfits/generate")
async def generate_outfit(req: OutfitRequest):
    """Generates an occasion-ready outfit recommendation respecting weather & dynamic taste memory."""
    items = req.available_items or database.get_clothing_items_by_user(req.user_id)
    if not items or len(items) < 2:
        raise HTTPException(status_code=400, detail="At least 2 items required in closet to curate an outfit.")

    # Fetch dynamic user taste memory (Pillar 2)
    taste_profile = database.get_user_taste_profile(req.user_id)

    w_dict = req.weather.model_dump() if hasattr(req.weather, "model_dump") else dict(req.weather or {})
    weather_payload = {
        "temp_c": w_dict.get("temperature_c", 20.0),
        "feels_like_c": w_dict.get("feels_like_c", w_dict.get("temperature_c", 20.0)),
        "condition": w_dict.get("condition", "Clear / Pleasant"),
        "is_raining": w_dict.get("is_raining", False),
        "display_location": w_dict.get("display_location", "Local")
    }

    return await stylist_service.generate_outfit_recommendation(
        client=genai_client,
        user_gender=req.user_gender,
        event_description=req.event_description,
        time_of_day=req.time_of_day,
        desired_vibe=req.desired_vibe,
        weather=weather_payload,
        items=items,
        taste_profile=taste_profile
    )


# =========================================================================
# TAB 4: SAVED LOOKBOOK ARCHIVES
# =========================================================================

@app.get("/api/v1/outfits/saved")
async def get_saved_outfits(user_id: str = Query(..., description="Active user ID")):
    """Fetches all favorited outfits and archived looks for the active user."""
    return database.get_saved_outfits_by_user(user_id)


@app.post("/api/v1/outfits/save")
async def save_outfit(payload: dict = Body(...)):
    """Saves a curated ensemble into the user's personal lookbook archive."""
    if not payload.get("user_id"):
        raise HTTPException(status_code=400, detail="user_id is required.")
    saved = database.save_outfit_record(payload)
    return {"status": "success", "outfit": saved}


@app.post("/api/v1/outfits/upload-worn")
async def upload_worn_outfit(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    title: str = Form("Past Favorite Look"),
    occasion: str = Form("Personal Archive"),
    notes: str = Form("")
):
    """Uploads a full-body worn look photo directly into the lookbook archive."""
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Empty photo upload.")

    timestamp = int(time.time())
    file_name = f"worn_looks/{user_id}_{timestamp}.png"
    image_url = cloud_storage.upload_image_bytes(raw_bytes, file_name, mime_type="image/jpeg")

    record = {
        "user_id": user_id,
        "title": title,
        "items": [],
        "image_url": image_url,
        "occasion": occasion,
        "rationale": notes
    }
    saved = database.save_outfit_record(record)
    return {"status": "success", "data": saved}


@app.delete("/api/v1/outfits/saved/{outfit_id}")
async def delete_saved_outfit(outfit_id: str):
    """Removes a look from the lookbook archive."""
    database.delete_saved_outfit_record(outfit_id)
    return {"status": "success"}


# =========================================================================
# WEATHER ENDPOINT
# =========================================================================

@app.get("/api/v1/weather")
async def get_live_weather(request: Request, location: Optional[str] = None):
    """Fetches real-time weather using device IP or manual query."""
    client_ip = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    if hasattr(weather_service, "fetch_weather_data"):
        return await weather_service.fetch_weather_data(manual_location=location, client_ip=client_ip)
    
    return {
        "city": "Sydney",
        "display_location": "Sydney, AU",
        "temperature_c": 21.0,
        "feels_like_c": 21.0,
        "condition": "Partly Cloudy & Pleasant",
        "wind_speed_kmh": 12.0,
        "is_raining": False
    }


# =========================================================================
# LOCAL EXECUTION ENTRYPOINT (Render runs via Uvicorn CLI start command)
# =========================================================================

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    print(f"=== LAUNCHING UVICORN ON 0.0.0.0:{port} ===", flush=True)

    try:
        # Pass the application as an import string, not the object directly
        uvicorn.run("backend.main:app", host="0.0.0.0", port=port, log_level="info")
    except Exception as e:
        print(f"CRITICAL STARTUP ERROR: {e}", flush=True)
        raise e

@app.api_route("/", methods=["GET", "HEAD"])
def health_check():
    """Lightweight health check endpoint accepting both GET and HEAD."""
    return {
        "status": "online",
        "service": "WoLo Wardrobe Backend",
        "time": time.time()
    }