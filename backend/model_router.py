import time
import json
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types

# Model tiers ordered by daily quota capacity and capability
INGESTION_CASCADE = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.7-flash",
    "gemini-2.5-flash"
]

STYLIST_CASCADE = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3-flash",
    "gemini-2.5-flash"
]

def generate_with_fallback(
    client: genai.Client,
    model_cascade: List[str],
    prompt: str,
    image_bytes: Optional[bytes] = None,
    mime_type: str = "image/jpeg",
    max_output_tokens: int = 700
) -> Dict[str, Any]:
    """
    Executes a structured JSON generation request across a dynamic model cascade.
    Falls back sequentially upon hitting 429 (ResourceExhausted) or service errors.
    """
    last_error = None

    for model_name in model_cascade:
        try:
            contents = []
            if image_bytes:
                contents.append(
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                )
            contents.append(prompt)

            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=max_output_tokens,
                    temperature=0.3
                )
            )

            raw_text = response.text.strip()
            # Clean possible markdown wrapping
            if raw_text.startswith("```json"):
                raw_text = raw_text.strip("```json").strip("```").strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.strip("```").strip()

            parsed = json.loads(raw_text)
            return {
                "success": True,
                "model_used": model_name,
                "data": parsed
            }

        except Exception as exc:
            err_msg = str(exc)
            last_error = err_msg
            print(f"[ModelRouter] Model '{model_name}' failed ({err_msg[:80]}...). Attempting fallback...")
            time.sleep(0.5)

    return {
        "success": False,
        "model_used": None,
        "error": last_error,
        "data": None
    }