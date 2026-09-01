import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from supabase import create_client, Client

# Load environment configuration from .env
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# Supabase Settings
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "wardrobe-photos")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[Config Warning] SUPABASE_URL or SUPABASE_KEY is missing from .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Gemini Client
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY must be configured in .env")

genai_client = genai.Client(api_key=GEMINI_API_KEY)