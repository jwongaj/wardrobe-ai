import os
import io
import time
import base64
from typing import Optional, List, Dict, Any

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
# Default to "items" or allow overriding via env
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "items")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client, Client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error initializing Supabase client in cloud_storage: {e}")


def ensure_bucket_exists():
    """Checks if the required storage bucket exists in Supabase, creates if missing."""
    if not supabase:
        return
    try:
        buckets = supabase.storage.list_buckets()
        bucket_names = [b.name for b in buckets]
        if STORAGE_BUCKET not in bucket_names:
            supabase.storage.create_bucket(STORAGE_BUCKET, options={"public": True})
            print(f"Created Supabase storage bucket: {STORAGE_BUCKET}")
    except Exception as e:
        print(f"Bucket existence check warning: {e}")


def upload_image_bytes(
    image_bytes: bytes,
    destination_path: str,
    mime_type: str = "image/png"
) -> str:
    """
    Uploads image bytes to Supabase Storage and returns a permanent public URL.
    Falls back gracefully to an inline Base64 Data URI if Supabase is offline.
    """
    if supabase:
        try:
            # Clean leading slashes
            clean_path = destination_path.lstrip("/")
            
            # Upsert into Supabase Storage
            supabase.storage.from_(STORAGE_BUCKET).upload(
                path=clean_path,
                file=image_bytes,
                file_options={"content-type": mime_type, "upsert": "true"}
            )
            
            # Retrieve permanent public URL
            public_url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(clean_path)
            if public_url:
                return public_url
        except Exception as e:
            print(f"Supabase upload failed ({destination_path}), using base64 fallback: {e}")

    # Zero-loss fallback: inline base64 data URI
    b64_str = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{b64_str}"


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
        print(f"Failed to download image ({file_path_or_url}): {e}")
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
        print(f"Failed to delete file {file_path_or_url}: {e}")
        return False