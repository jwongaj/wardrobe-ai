import os
import sys
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

import database
from cloud_storage import supabase, SUPABASE_BUCKET


def purge_orphaned_supabase_images(dry_run: bool = True):
    """
    Finds and deletes files in Supabase Storage that are not linked to any SQLite wardrobe item.
    :param dry_run: If True, only lists orphaned files without deleting them.
    """
    print(f"--- Starting Supabase Storage Audit (dry_run={dry_run}) ---")

    # 1. Fetch all active image URLs from SQLite
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT image_url FROM clothing_items WHERE image_url IS NOT NULL AND image_url != ''")
    rows = cursor.fetchall()
    conn.close()

    active_paths = set()
    for row in rows:
        url = row["image_url"] if isinstance(row, dict) else row[0]
        # Extract relative path inside the bucket (e.g. 'items/jas_123.png')
        parsed = urlparse(url)
        path_parts = parsed.path.split(f"/public/{SUPABASE_BUCKET}/")
        if len(path_parts) > 1:
            active_paths.add(path_parts[1])
        else:
            active_paths.add(url.split("/")[-1])

    print(f"✓ Found {len(active_paths)} active image references in SQLite.")

    # 2. List all files in the Supabase 'items' folder
    try:
        storage_files = supabase.storage.from_(SUPABASE_BUCKET).list("items")
    except Exception as e:
        print(f"Error connecting to Supabase Storage: {e}")
        return

    if not storage_files:
        print("No files found in the 'items' directory.")
        return

    orphaned_paths = []
    for f in storage_files:
        file_name = f.get("name")
        if not file_name or file_name.startswith("."):
            continue

        full_rel_path = f"items/{file_name}"
        if full_rel_path not in active_paths and file_name not in active_paths:
            orphaned_paths.append(full_rel_path)

    print(f"✓ Total files scanned in bucket: {len(storage_files)}")
    print(f"✓ Orphaned / unlinked files found: {len(orphaned_paths)}")

    # 3. Handle Deletion or Preview
    if not orphaned_paths:
        print("🎉 Your Supabase Storage is completely clean! No unlinked images.")
        return

    if dry_run:
        print("\n[DRY RUN PREVIEW] The following files are NOT linked in your database:")
        for p in orphaned_paths:
            print(f"  - {p}")
        print("\nTo permanently delete these files, run: python cleanup_storage.py --delete")
    else:
        print(f"\nDeleting {len(orphaned_paths)} unlinked files from Supabase Storage...")
        # Supabase allows deleting in batches
        res = supabase.storage.from_(SUPABASE_BUCKET).remove(orphaned_paths)
        print(f"✓ Clean up complete! Removed: {res}")


if __name__ == "__main__":
    should_delete = "--delete" in sys.argv
    purge_orphaned_supabase_images(dry_run=not should_delete)