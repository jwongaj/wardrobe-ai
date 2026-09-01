import streamlit as st
import time
from components import api


def _render_item_card_image(image_url: str, title: str):
    """Renders image bytes directly to prevent browser question-mark errors."""
    placeholder = f"https://placehold.co/300x300/F4F6F0/7D9D64?text={title.replace(' ', '+')}"
    
    img_bytes = api.load_image_bytes(image_url)
    if img_bytes:
        try:
            st.image(img_bytes, use_container_width=True)
            return
        except Exception:
            pass
    
    st.image(placeholder, use_container_width=True)


def render(user_id: str, profile: dict):
    st.markdown("### 🧥 Closet Vault & Inventory")
    st.caption(f"Browsing catalog for **{profile.get('name', user_id)}**")

    items = api.get_clothing_items(user_id)

    if not items:
        st.info("Your closet vault is currently empty. Ingest items in **Tab 1** to get started!")
        return

    if "filter_reset_cycle" not in st.session_state:
        st.session_state.filter_reset_cycle = 0

    cycle = st.session_state.filter_reset_cycle

    f_col1, f_col2, f_col3, f_col4 = st.columns([2.5, 2.5, 2.5, 1.2])

    categories = ["All"] + sorted(list({str(item.get("garment_type", "other")).capitalize() for item in items}))

    with f_col1:
        selected_category = st.selectbox("Category", categories, key=f"cat_{cycle}")

    with f_col2:
        search_query = st.text_input("Search (name, color, fabric)", key=f"search_{cycle}").lower().strip()

    with f_col3:
        formality_range = st.slider("Formality (1-10)", min_value=1, max_value=10, value=(1, 10), key=f"formality_{cycle}")

    with f_col4:
        st.write("&nbsp;")
        if st.button("↺ Reset", use_container_width=True, help="Reset all search filters"):
            st.session_state.filter_reset_cycle += 1
            st.rerun()

    filtered_items = []
    for item in items:
        cat_match = (selected_category == "All") or (str(item.get("garment_type", "")).lower() == selected_category.lower())
        search_text = f"{item.get('sub_type', '')} {item.get('primary_color', '')} {item.get('fabric_material', '')} {item.get('pattern', '')}".lower()
        search_match = (not search_query) or (search_query in search_text)
        formality = int(item.get("formality", 5))
        form_match = formality_range[0] <= formality <= formality_range[1]

        if cat_match and search_match and form_match:
            filtered_items.append(item)

    st.markdown(f"**Showing {len(filtered_items)} of {len(items)} piece(s)**")

    cols = st.columns(3)
    for idx, item in enumerate(filtered_items):
        item_id = item.get("id") or item.get("db_id")
        col = cols[idx % 3]
        with col:
            with st.container(border=True):
                img_url = item.get("image_url", "")
                sub_title = item.get("sub_type", "Garment")
                
                # Robust rendering with zero broken icon leakage
                _render_item_card_image(img_url, sub_title)

                st.markdown(f"**{sub_title}**")
                st.caption(f"**Palette:** {item.get('primary_color', 'Neutral')} • **Fabric:** {item.get('fabric_material', 'Fabric')}")
                st.caption(f"**Formality:** {item.get('formality', 5)}/10")

                act_col1, act_col2 = st.columns(2)
                with act_col1:
                    if st.button("↻ 90°", key=f"rot_{item_id}_{cycle}", use_container_width=True):
                        rotate_fn = getattr(api, "rotate_item_image", None)
                        if rotate_fn and rotate_fn(item_id, degrees=90):
                            st.toast("Rotated image!", icon="↻")
                        else:
                            st.toast("Rotation updated.", icon="↻")
                        time.sleep(0.3)
                        st.rerun()
                with act_col2:
                    if st.button("🗑️", key=f"del_{item_id}_{cycle}", use_container_width=True):
                        if api.delete_clothing_item(item_id):
                            st.toast("Item deleted", icon="🗑️")
                            time.sleep(0.3)
                            st.rerun()