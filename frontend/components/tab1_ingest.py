import streamlit as st
import time
from components import api

GARMENT_CATEGORIES = ["top", "bottom", "dress", "outerwear", "shoes", "accessory", "jewelry"]


def render(user_id: str, profile: dict):
    st.markdown("### 📸 Ingest & Digitize")
    st.caption(f"Digitizing wardrobe pieces for **{profile.get('name', user_id)}**")

    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "staged_ingestion_items" not in st.session_state:
        st.session_state.staged_ingestion_items = []
    if "pending_duplicates" not in st.session_state:
        st.session_state.pending_duplicates = []
    if "last_ingest_errors" not in st.session_state:
        st.session_state.last_ingest_errors = []

    # Display persistent errors from previous run if any
    if st.session_state.last_ingest_errors:
        for err in st.session_state.last_ingest_errors:
            st.error(f"❌ {err}")
        if st.button("Dismiss Errors", key="btn_clear_errors"):
            st.session_state.last_ingest_errors = []
            st.rerun()

    # =========================================================================
    # 1. DUPLICATE RESOLUTION MODAL
    # =========================================================================
    if st.session_state.pending_duplicates:
        st.warning("🔍 **Potential Duplicate Pieces Detected**")
        st.caption("Review these items side-by-side to choose whether to replace, keep both, or discard.")

        for idx, pending in enumerate(list(st.session_state.pending_duplicates)):
            existing = pending.get("matched_existing", {})
            existing_id = existing.get("id") or existing.get("db_id")

            with st.container(border=True):
                st.markdown(f"#### `{pending.get('sub_type')}` vs `{existing.get('sub_type')}`")
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**✨ Newly Detected**")
                    img_new = pending.get("image_url", "")
                    st.markdown(
                        f"""
                        <div style="background: #F4F6F0; border-radius: 8px; padding: 8px; display: flex; align-items: center; justify-content: center; min-height: 140px; border: 1px solid #E2E8DC; margin-bottom: 6px;">
                            <img src="{img_new}" style="max-height: 120px; max-width: 100%; object-fit: contain;" onerror="this.onerror=null; this.src='https://placehold.co/120x120/F4F6F0/7D9D64?text=New+Item';" />
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.caption(f"{pending.get('primary_color')} • {pending.get('fabric_material')}")

                with c2:
                    st.markdown("**🧥 In Closet Vault**")
                    img_ex = existing.get("image_url", "")
                    st.markdown(
                        f"""
                        <div style="background: #F4F6F0; border-radius: 8px; padding: 8px; display: flex; align-items: center; justify-content: center; min-height: 140px; border: 1px solid #E2E8DC; margin-bottom: 6px;">
                            <img src="{img_ex}" style="max-height: 120px; max-width: 100%; object-fit: contain;" onerror="this.onerror=null; this.src='https://placehold.co/120x120/F4F6F0/7D9D64?text=Existing+Item';" />
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.caption(f"{existing.get('primary_color')} • {existing.get('fabric_material')}")

                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("➕ Keep Both", key=f"dup_keep_{idx}", use_container_width=True):
                        st.session_state.staged_ingestion_items.append(pending)
                        st.session_state.pending_duplicates.pop(idx)
                        st.rerun()
                with b2:
                    if st.button("🔄 Replace Old Photo", key=f"dup_rep_{idx}", use_container_width=True):
                        api.update_item_image(existing_id, pending.get("image_url"))
                        st.session_state.pending_duplicates.pop(idx)
                        st.toast("Updated closet photo!", icon="📸")
                        st.rerun()
                with b3:
                    if st.button("🗑️ Discard New", key=f"dup_disc_{idx}", use_container_width=True):
                        st.session_state.pending_duplicates.pop(idx)
                        st.rerun()
        st.divider()

    # =========================================================================
    # 2. FILE UPLOADER
    # =========================================================================
    uploaded_files = st.file_uploader(
        "Upload garment photos or flat-lays\n\nJPG, PNG, HEIC, WEBP",
        type=["jpg", "jpeg", "png", "heic", "webp"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_key}"
    )

    if uploaded_files:
        st.write(f"📁 **{len(uploaded_files)}** file(s) selected for processing.")
        if st.button("✨ Detect & Stage Items", type="primary", use_container_width=True):
            staged = []
            dups = []
            errors = []

            # 1. Ping health to wake up cold container if needed
            with st.spinner("Connecting to styling engine..."):
                if not api.check_health():
                    time.sleep(2)

            # 2. Process uploads sequentially
            progress_bar = st.progress(0, text="Starting AI vision cataloging...")
            total_files = len(uploaded_files)

            for idx, file_obj in enumerate(uploaded_files):
                progress_bar.progress(
                    (idx) / total_files,
                    text=f"Analyzing {file_obj.name} ({idx + 1}/{total_files})..."
                )

                res = api.ingest_image(
                    file_obj,
                    user_id=user_id,
                    user_gender=profile.get("gender", "Womenswear")
                )

                if res.get("status") == "success":
                    for itm in res.get("items", []):
                        if "stage_id" not in itm:
                            itm["stage_id"] = f"stg_{int(time.time() * 1000)}_{len(staged)}"
                        staged.append(itm)
                    dups.extend(res.get("pending_duplicates", []))
                else:
                    err_msg = res.get("error", "Unknown ingestion error.")
                    errors.append(f"**{file_obj.name}**: {err_msg}")

            progress_bar.progress(1.0, text="Ingestion complete!")
            time.sleep(0.4)

            # Persist state
            st.session_state.last_ingest_errors = errors
            if staged:
                st.session_state.staged_ingestion_items.extend(staged)
            if dups:
                st.session_state.pending_duplicates.extend(dups)

            if staged or dups:
                st.session_state.uploader_key += 1

            st.rerun()

    # =========================================================================
    # 3. STAGED REVIEW & EDIT BEFORE FINAL COMMIT
    # =========================================================================
    if st.session_state.staged_ingestion_items:
        st.markdown("---")
        st.markdown(f"### 📋 Review & Edit Staged Items ({len(st.session_state.staged_ingestion_items)})")
        st.caption("Verify detections before committing to your permanent Closet Vault. Adjust categories, formality, or remove false positives.")

        for idx, item in enumerate(list(st.session_state.staged_ingestion_items)):
            stage_key = item.get("stage_id", f"stg_{idx}")

            with st.container(border=True):
                c_img, c_edit, c_del = st.columns([1.2, 3, 0.8])
                with c_img:
                    img_url = item.get("image_url", "")
                    st.markdown(
                        f"""
                        <div style="background: #F4F6F0; border-radius: 8px; padding: 8px; display: flex; align-items: center; justify-content: center; min-height: 150px; border: 1px solid #E2E8DC;">
                            <img src="{img_url}" style="max-height: 135px; max-width: 100%; object-fit: contain;" onerror="this.onerror=null; this.src='https://placehold.co/135x135/F4F6F0/7D9D64?text={item.get('sub_type', 'Garment').replace(' ', '+')}';" />
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                with c_edit:
                    e1, e2 = st.columns(2)
                    with e1:
                        item["sub_type"] = st.text_input("Item Name", value=item.get("sub_type", "Garment"), key=f"name_{stage_key}")
                        curr_cat = str(item.get("garment_type", "top")).lower()
                        cat_idx = GARMENT_CATEGORIES.index(curr_cat) if curr_cat in GARMENT_CATEGORIES else 0
                        item["garment_type"] = st.selectbox("Category", GARMENT_CATEGORIES, index=cat_idx, key=f"cat_{stage_key}")
                    with e2:
                        item["primary_color"] = st.text_input("Primary Color", value=item.get("primary_color", "Neutral"), key=f"col_{stage_key}")
                        item["fabric_material"] = st.text_input("Fabric Material", value=item.get("fabric_material", "Fabric"), key=f"fab_{stage_key}")

                    item["formality"] = st.slider("Formality Baseline (1: Casual → 10: Formal)", 1, 10, int(item.get("formality", 5)), key=f"form_{stage_key}")

                with c_del:
                    st.write("&nbsp;")
                    if st.button("🗑️ Remove", key=f"del_{stage_key}", use_container_width=True, help="Discard falsely detected item"):
                        st.session_state.staged_ingestion_items.pop(idx)
                        st.toast("Item discarded from stage.", icon="🗑️")
                        time.sleep(0.2)
                        st.rerun()

        st.write("")
        col_commit, col_clear = st.columns([3, 1])
        with col_commit:
            if st.button("✅ Confirm & Save All to Closet Vault", type="primary", use_container_width=True):
                with st.spinner("Saving to your persistent database..."):
                    for itm in st.session_state.staged_ingestion_items:
                        api.save_single_item(itm)
                st.session_state.staged_ingestion_items = []
                st.toast("All verified items added to your Closet Vault!", icon="👗")
                time.sleep(0.3)
                st.rerun()

        with col_clear:
            if st.button("Cancel All", use_container_width=True):
                st.session_state.staged_ingestion_items = []
                st.rerun()