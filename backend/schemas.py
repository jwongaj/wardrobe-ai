from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ==========================================
# --- ENUMS ---
# ==========================================

class GarmentType(str, Enum):
    top = "top"
    bottom = "bottom"
    one_piece = "one_piece"
    dress = "dress"
    outerwear = "outerwear"
    footwear = "footwear"
    accessory = "accessory"


class PatternType(str, Enum):
    solid = "solid"
    striped = "striped"
    plaid = "plaid"
    floral = "floral"
    graphic = "graphic"
    geometric = "geometric"
    other = "other"


class Season(str, Enum):
    spring = "spring"
    summer = "summer"
    autumn = "autumn"
    winter = "winter"


class WeatherCondition(str, Enum):
    hot = "hot"
    warm = "warm"
    mild = "mild"
    cool = "cool"
    cold = "cold"
    rainy = "rainy"
    windy = "windy"


class BinaryRating(str, Enum):
    thumbs_up = "thumbs_up"
    thumbs_down = "thumbs_down"


# ==========================================
# --- CLOTHING ITEM SCHEMAS ---
# ==========================================

class ClothingItem(BaseModel):
    id: Optional[Any] = None
    db_id: Optional[Any] = None
    user_id: Optional[str] = None
    garment_type: str
    sub_type: Optional[str] = "Garment"
    primary_color: str
    secondary_colors: List[str] = Field(default_factory=list)
    pattern: str = "solid"
    fabric_material: str = "cotton"
    formality: int = Field(default=5, ge=1, le=10)
    seasons: List[str] = Field(default_factory=list)
    style_tags: List[str] = Field(default_factory=list)
    dominant_color_hex: Optional[str] = "#CCCCCC"
    image_url: Optional[str] = None
    box_2d: Optional[List[int]] = None

    class Config:
        from_attributes = True


# Aliases for backward compatibility
ClothingItemTags = ClothingItem
ClothingItemMetadata = ClothingItem


# ==========================================
# --- INGESTION SCHEMAS ---
# ==========================================

class IngestionResponse(BaseModel):
    status: str = "success"
    message: Optional[str] = None
    detected_count: int = 0
    ingested_count: int = 0
    items: List[Dict[str, Any]] = Field(default_factory=list)
    pending_duplicates: List[Dict[str, Any]] = Field(default_factory=list)


# ==========================================
# --- WEATHER & OUTFIT SCHEMAS ---
# ==========================================

class WeatherInfo(BaseModel):
    temperature_c: float = 20.0
    feels_like_c: Optional[float] = None
    condition: str = "Clear / Pleasant"
    is_raining: bool = False
    display_location: Optional[str] = "Local"


# Alias for backward compatibility
WeatherContext = WeatherInfo


class OutfitRequest(BaseModel):
    user_id: str
    user_gender: str = "women"
    event_description: str = "Casual day out"
    time_of_day: str = "Morning"
    desired_vibe: str = "Effortless chic"
    weather: Optional[WeatherInfo] = Field(default_factory=WeatherInfo)
    available_items: Optional[List[Dict[str, Any]]] = Field(default_factory=list)


class OutfitResponse(BaseModel):
    title: str = "Curated Ensemble"
    rationale: str
    items: List[Dict[str, Any]] = Field(default_factory=list)
    selected_item_ids: Optional[List[Any]] = Field(default_factory=list)


# ==========================================
# --- PILLAR 2: TASTE MEMORY & FEEDBACK SCHEMAS ---
# ==========================================

class BinaryFeedbackPayload(BaseModel):
    user_id: str
    outfit_id: Optional[str] = None
    rating: str  # "thumbs_up" | "thumbs_down"
    chips: List[str] = Field(default_factory=list)
    outfit_items: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    notes: Optional[str] = None


# Alias for backward compatibility
OutfitFeedback = BinaryFeedbackPayload


class UpdateTasteTagsPayload(BaseModel):
    user_id: str
    active_tags: List[str] = Field(default_factory=list)
    avoided_tags: Optional[List[str]] = Field(default_factory=list)


class TasteProfileResponse(BaseModel):
    user_id: str
    aesthetic_summary: str
    target_formality: float = 4.5
    active_tags: List[str] = Field(default_factory=list)
    suggested_tags: List[str] = Field(default_factory=list)
    avoided_tags: List[str] = Field(default_factory=list)
    tag_weights: Dict[str, float] = Field(default_factory=dict)
    thumbs_up_count: int = 0
    thumbs_down_count: int = 0
    updated_at: Optional[int] = None


# ==========================================
# --- LOOKBOOK SCHEMAS ---
# ==========================================

class SavedOutfitCreate(BaseModel):
    user_id: str
    title: str = "Curated Look"
    occasion: Optional[str] = "Everyday"
    items: List[Dict[str, Any]] = Field(default_factory=list)
    rationale: Optional[str] = None
    image_url: Optional[str] = None
    created_at: Optional[str] = None


