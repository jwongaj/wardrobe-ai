import os
import io
import time
import base64
from typing import Optional, List, Dict, Any

from config import supabase

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "wardrobe-photos")


def ensure_bucket_exists():
    """Checks if the required storage bucket exists in Supabase, creates if missing."""
    if not supabase:
        return
    try:
        buckets = supabase.storage.list_buckets()
        bucket_names = [b.name for b in buckets]
        if STORAGE_BUCKET not in bucket_names:
            supabase.storage.create_bucket(STORAGE_BUCKET, options={"public": True})
            print(f"Created Supabase storage bucket: {STORAGE_BUCKET}", flush=True)
    except Exception as e:
        print(f"Bucket existence check warning: {e}", flush=True)


def upload_image_bytes(image_bytes: bytes, destination_path: str, mime_type: str = "image/jpeg") -> str:
    """
    Uploads raw image bytes to Supabase Storage and returns the public CDN URL.
    Safely strips duplicate bucket prefixes from destination_path.
    """
    if not supabase:
        print("[STORAGE WARNING] No supabase client initialized. Using inline base64 fallback.", flush=True)
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{b64}"

    clean_path = destination_path.lstrip("/")
    if clean_path.startswith(f"{STORAGE_BUCKET}/"):
        clean_path = clean_path[len(STORAGE_BUCKET) + 1:]

    try:
        # Upload with upsert enabled
        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=clean_path,
            file=image_bytes,
            file_options={"content-type": mime_type, "upsert": "true"}
        )

        # Retrieve CDN public URL
        public_url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(clean_path)
        return public_url

    except Exception as e:
        print(f"[STORAGE UPLOAD ERROR] {clean_path}: {e}", flush=True)
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{b64}"


def resolve_image_url(raw_url: str) -> str:
    """
    Guarantees any legacy relative path or key is converted
    into a valid public URL or base64 URI.
    """
    if not raw_url:
        return ""
    if raw_url.startswith("data:") or raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    if SUPABASE_URL:
        clean_path = raw_url.lstrip("/")
        return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{clean_path}"
    return raw_url


def download_image_bytes(file_path_or_url: str) -> bytes:
    """
    Downloads raw image bytes from Supabase storage or decodes inline Base64 data.
    """
    if file_path_or_url.startswith("data:"):
        header, b64data = file_path_or_url.split(",", 1)
        return base64.b64decode(b64data)

    if not supabase:
        raise RuntimeError("Supabase client is not configured for image download.")

    try:
        path = file_path_or_url
        if f"{STORAGE_BUCKET}/" in path:
            path = path.split(f"{STORAGE_BUCKET}/")[-1].split("?")[0]
        else:
            path = path.lstrip("/")

        return supabase.storage.from_(STORAGE_BUCKET).download(path)
    except Exception as e:
        print(f"Failed to download image ({file_path_or_url}): {e}", flush=True)
        raise e


def delete_file(file_path_or_url: str) -> bool:
    """Deletes a single file from storage by path or URL."""
    if not supabase or file_path_or_url.startswith("data:"):
        return False
    try:
        path = file_path_or_url
        if f"{STORAGE_BUCKET}/" in path:
            path = path.split(f"{STORAGE_BUCKET}/")[-1].split("?")[0]
        else:
            path = path.lstrip("/")

        supabase.storage.from_(STORAGE_BUCKET).remove([path])
        return True
    except Exception as e:
        print(f"Failed to delete file {file_path_or_url}: {e}", flush=True)
        return False