import streamlit as st
import time
from components import api

MAX_ACTIVE_TAGS = 6


def render(user_id: str, profile: dict):
    st.markdown("### 📖 The Lookbook & Taste Algorithm")
    st.caption(f"Curated archives & evolving style algorithm for **{profile.get('name', user_id)}**")

    # =========================================================================
    # 1. "YOUR STYLE ALGORITHM" HEADER
    # =========================================================================
    taste_profile = api.get_taste_profile(user_id)
    active_tags = taste_profile.get("active_tags", [])
    suggested_tags = taste_profile.get("suggested_tags", [])
    summary = taste_profile.get(
        "aesthetic_summary",
        "An effortless blend of luminous minimalism and relaxed tailoring with high affinity for neutral linens and subtle structure."
    )

    with st.container(border=True):
        st.markdown("#### 🧠 Your Style Algorithm")
        st.markdown(
            f"""
            <div style="background: #F0F4EC; border-left: 4px solid #7D9D64; padding: 12px 16px; border-radius: 6px; margin-bottom: 12px;">
                <p style="margin: 0; font-size: 15px; color: #2C3E2D; font-weight: 500;">
                    <em>"{summary}"</em>
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.caption(f"Active Labels ({len(active_tags)}/{MAX_ACTIVE_TAGS} max). Click ✕ to remove or ➕ to add.")

        col_act, col_sug = st.columns([1.2, 1])
        with col_act:
            st.markdown(f"**Active Aesthetic Labels ({len(active_tags)}/{MAX_ACTIVE_TAGS}):**")
            if active_tags:
                tag_cols = st.columns(min(len(active_tags), 3))
                for idx, tag in enumerate(list(active_tags)):
                    c = tag_cols[idx % 3]
                    with c:
                        if st.button(f"{tag} ✕", key=f"del_tag_{tag}", help=f"Remove '{tag}'"):
                            updated_active = [t for t in active_tags if t != tag]
                            api.update_taste_tags(user_id, updated_active)
                            st.toast(f"Removed '{tag}'.", icon="✂️")
                            time.sleep(0.2)
                            st.rerun()
            else:
                st.caption("No active labels.")

        with col_sug:
            st.markdown("**AI Suggestions Based on Learnings:**")
            if suggested_tags:
                sug_cols = st.columns(min(len(suggested_tags), 2))
                for idx, sug in enumerate(suggested_tags):
                    sc = sug_cols[idx % 2]
                    with sc:
                        if st.button(f"➕ {sug}", key=f"add_tag_{sug}", help=f"Add '{sug}'"):
                            if len(active_tags) >= MAX_ACTIVE_TAGS:
                                st.warning(f"Maximum {MAX_ACTIVE_TAGS} active labels reached. Remove one first.")
                            else:
                                updated_active = active_tags + [sug]
                                api.update_taste_tags(user_id, updated_active)
                                st.toast(f"Added '{sug}'!", icon="✨")
                                time.sleep(0.2)
                                st.rerun()

    st.markdown("---")

    # =========================================================================
    # 2. SAVED LOOKBOOK ARCHIVES
    # =========================================================================
    saved_looks = api.get_saved_outfits(user_id)
    if not saved_looks:
        st.info("No saved looks found yet. Style outfits in **Tab 3** and click 'Save Look to Lookbook'!")
        return

    st.markdown(f"**Total Looks in Archive: {len(saved_looks)}**")

    cols = st.columns(2)
    for idx, look in enumerate(saved_looks):
        look_id = look.get("id", idx)
        col = cols[idx % 2]

        # Clean title strictly without hardcoded emojis
        raw_title = look.get("title", "Curated Look")
        clean_title = raw_title.replace("🥂", "").replace("✨", "").strip()

        with col:
            with st.container(border=True):
                st.markdown(f"#### {clean_title}")
                st.caption(f"**Occasion:** {look.get('occasion', 'General')} • **Date:** {look.get('created_at', 'Recent')}")

                # Garment cards display with fallback image handler
                items = look.get("items", [])
                if items:
                    item_cols = st.columns(min(len(items), 3))
                    for i_idx, itm in enumerate(items):
                        with item_cols[i_idx % 3]:
                            img_url = itm.get("image_url", "")
                            sub_title = itm.get("sub_type", "Garment")
                            if img_url:
                                st.markdown(
                                    f"""
                                    <div style="background: #F4F6F0; border-radius: 8px; padding: 6px; display: flex; align-items: center; justify-content: center; min-height: 110px; margin-bottom: 4px; border: 1px solid #E2E8DC;">
                                        <img src="{img_url}" style="max-height: 95px; max-width: 100%; object-fit: contain;" onerror="this.onerror=null; this.src='https://placehold.co/95x95/F4F6F0/7D9D64?text={sub_title.replace(' ', '+')}';" />
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                            st.caption(f"**{sub_title}**")
                elif look.get("image_url"):
                    st.image(look.get("image_url"), use_container_width=True)

                rationale_text = look.get("styling_notes") or look.get("rationale")
                if rationale_text:
                    st.markdown(
                        f"""
                        <div style="background: #F9FAF6; border-left: 3px solid #6C8E64; padding: 10px 14px; font-size: 0.88rem; border-radius: 4px; margin: 8px 0; color: #2D4A27;">
                            {rationale_text}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                b_col1, b_col2, b_col3 = st.columns([1, 1, 1.5])
                with b_col1:
                    if st.button("👍", key=f"lk_up_{look_id}", use_container_width=True):
                        api.submit_binary_feedback(user_id=user_id, rating="thumbs_up", chips=[], outfit_items=items, outfit_id=str(look_id))
                        st.toast("Taste memory reinforced!", icon="👍")
                with b_col2:
                    if st.button("👎", key=f"lk_dn_{look_id}", use_container_width=True):
                        api.submit_binary_feedback(user_id=user_id, rating="thumbs_down", chips=[], outfit_items=items, outfit_id=str(look_id))
                        st.toast("Taste memory updated!", icon="👎")
                with b_col3:
                    if st.button("🗑️ Remove", key=f"del_look_{look_id}", use_container_width=True):
                        api.delete_saved_outfit(str(look_id))
                        st.toast("Look removed.", icon="🗑️")
                        time.sleep(0.2)
                        st.rerun()