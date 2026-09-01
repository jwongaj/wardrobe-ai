import streamlit as st
import os
import json
import re
import time
import datetime
from components import (
    api,
    tab1_ingest,
    tab2_wardrobe,
    tab3_stylist,
    tab4_lookbook
)

PROFILES_FILE = os.path.join(os.path.dirname(__file__), "profiles.json")

st.set_page_config(
    page_title="✨ WoLo Wardrobe — Style Booboos Up",
    page_icon="🧚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STORYBOOK SCRIPT & MINIMALIST THEME CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Alex+Brush&family=Allura&family=Great+Vibes&family=IM+Fell+English:ital@0;1&family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&family=Playfair+Display:ital,wght@0,600;0,700;1,400&display=swap');

    :root { color-scheme: light !important; }
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #1F271B;
    }
    .stApp { background: linear-gradient(180deg, #FAFBF8 0%, #F1F5EB 100%); }
    .wolo-title {
        font-family: 'Great Vibes', 'Allura', 'Alex Brush', cursive !important;
        font-size: 3.8rem !important;
        color: #384F33 !important;
        margin-bottom: 0.1rem !important;
        line-height: 1.15 !important;
        text-shadow: 1px 2px 4px rgba(45, 74, 39, 0.08);
    }
    .wolo-tagline {
        font-family: 'IM Fell English', serif;
        font-size: 1.05rem;
        color: #5C6E53;
        font-style: italic;
        margin-bottom: 1.2rem;
    }
    h2, h3, h4 {
        font-family: 'Playfair Display', serif !important;
        font-weight: 600 !important;
        color: #22381F;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 20px;
        background-color: transparent;
        border-bottom: 1.5px solid #DCE5D3;
        padding-bottom: 6px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        background-color: transparent;
        color: #6C7A65;
        font-size: 0.94rem;
        font-weight: 500;
        border: none;
        padding: 0 12px;
    }
    .stTabs [aria-selected="true"] {
        color: #2D4A27 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #384F33 !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2E4B28 0%, #3D6436 100%) !important;
        color: #FFFFFF !important;
        border-radius: 28px !important;
        padding: 0.65rem 2.2rem !important;
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(46, 75, 40, 0.18) !important;
    }
    .atelier-pill {
        display: inline-block;
        padding: 4px 11px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        margin: 2px 4px 2px 0px;
    }
    .pill-type { background-color: #EBF2E4; color: #2D4A27; border: 1px solid #D7E5CC; }
    .pill-formality { background-color: #F8F3DC; color: #785A14; border: 1px solid #EFE4BD; }
    .pixie-verdict-box {
        background: #1E281C;
        border-left: 4px solid #DFB15B;
        padding: 16px 20px;
        margin: 16px 0 24px 0;
        border-radius: 0 12px 12px 0;
    }
</style>
""", unsafe_allow_html=True)


# --- PROFILE PERSISTENCE HELPERS ---
def load_profiles() -> dict:
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_profiles(profiles_data: dict):
    with open(PROFILES_FILE, "w") as f:
        json.dump(profiles_data, f, indent=2)

def rename_profile(old_id: str, new_name: str, new_gender: str, new_style: str):
    all_profiles = load_profiles()
    if old_id in all_profiles:
        all_profiles[old_id]["name"] = new_name.strip()
        all_profiles[old_id]["gender"] = new_gender
        all_profiles[old_id]["default_style"] = new_style.strip()
        save_profiles(all_profiles)

def delete_profile(user_id: str):
    all_profiles = load_profiles()
    if user_id in all_profiles:
        del all_profiles[user_id]
        save_profiles(all_profiles)


profiles = load_profiles()
query_params = st.query_params
url_user_id = query_params.get("user")

if "active_user_id" not in st.session_state:
    if url_user_id and url_user_id in profiles:
        st.session_state["active_user_id"] = url_user_id
    elif profiles:
        st.session_state["active_user_id"] = list(profiles.keys())[0]
    else:
        st.session_state["active_user_id"] = None


# ==========================================
# --- ONBOARDING GATE (FIRST TIME SETUP) ---
# ==========================================
if not st.session_state["active_user_id"] or st.session_state.get("creating_new_profile"):
    st.markdown('<div class="wolo-title">✨ WoLo Wardrobe</div>', unsafe_allow_html=True)
    st.markdown('<p class="wolo-tagline">Style booboos up to be the prince and princess of the hour.</p>', unsafe_allow_html=True)

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Who are we styling?", placeholder="Your name")
        with col2:
            gender = st.selectbox("Tailoring Preference", ["Womenswear", "Menswear", "Gender-Neutral"])
        
        style_notes = st.text_input("Default Aesthetic", placeholder="e.g. Luminous Minimalism, sharp tailoring, quiet luxury")
        submit_btn = st.button("✨ Initialize Wardrobe", type="primary", use_container_width=True)

        if submit_btn:
            if full_name.strip():
                clean_id = re.sub(r'[^a-zA-Z0-9_]', '', full_name.strip().lower().replace(" ", "_")) or f"user_{int(time.time())}"
                profiles[clean_id] = {
                    "id": clean_id,
                    "name": full_name.strip(),
                    "gender": gender,
                    "default_style": style_notes.strip() or "Modern Minimalist",
                    "created_at": str(datetime.datetime.now())
                }
                save_profiles(profiles)
                st.session_state["active_user_id"] = clean_id
                st.session_state["creating_new_profile"] = False
                st.query_params["user"] = clean_id
                st.rerun()

    if profiles and st.session_state.get("creating_new_profile"):
        if st.button("← Return to Existing Wardrobe"):
            st.session_state["creating_new_profile"] = False
            st.rerun()
    st.stop()


# ==========================================
# --- SIDEBAR: PROFILE, SETTINGS & ADMIN ---
# ==========================================
current_user_id = st.session_state["active_user_id"]
current_profile = profiles.get(current_user_id, {
    "name": current_user_id,
    "gender": "Womenswear",
    "default_style": "Modern Minimalist"
})

with st.sidebar:
    online = api.check_health()
    if online:
        st.markdown(
            """
            <div style="display: inline-flex; align-items: center; background-color: #EBF5E7; padding: 5px 12px; border-radius: 12px; border: 1px solid #CEE5C5; margin-bottom: 12px;">
                <span style="height: 7px; width: 7px; background-color: #38A169; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
                <span style="font-size: 0.78rem; font-weight: 600; color: #22543D; letter-spacing: 0.02em;">SYSTEM ONLINE</span>
            </div>
            """, 
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div style="display: inline-flex; align-items: center; background-color: #FDF0ED; padding: 5px 12px; border-radius: 12px; border: 1px solid #F5C7BC; margin-bottom: 12px;">
                <span style="height: 7px; width: 7px; background-color: #E53E3E; border-radius: 50%; display: inline-block; margin-right: 8px;"></span>
                <span style="font-size: 0.78rem; font-weight: 600; color: #742A2A; letter-spacing: 0.02em;">DISCONNECTED</span>
            </div>
            """, 
            unsafe_allow_html=True
        )

    st.markdown("### 🧚 Wardrobes")
    profiles = load_profiles()
    profile_keys = list(profiles.keys())
    current_idx = profile_keys.index(current_user_id) if current_user_id in profile_keys else 0

    selected_user = st.selectbox(
        "Active Profile",
        options=profile_keys,
        index=current_idx,
        format_func=lambda k: f"{profiles[k].get('name', k)} ({profiles[k].get('gender', 'Womenswear')})",
        key="profile_selector"
    )

    if selected_user != current_user_id:
        st.session_state["active_user_id"] = selected_user
        st.query_params["user"] = selected_user
        st.rerun()

    st.write("")

    if st.button("＋ Add Another Profile", use_container_width=True):
        st.session_state["creating_new_profile"] = True
        st.rerun()

    st.divider()

    # --- EDIT PROFILE DETAILS ---
    with st.expander("⚙️ Edit Profile Details", expanded=False):
        st.markdown(f"**Editing:** `{current_profile.get('name')}`")

        edit_name = st.text_input(
            "Name", 
            value=current_profile.get("name", ""),
            key=f"edit_name_{current_user_id}"
        )
        
        gender_options = ["Womenswear", "Menswear", "Gender-Neutral"]
        cur_gender = current_profile.get("gender", "Womenswear")
        if cur_gender not in gender_options:
            cur_gender = "Womenswear" if "Women" in cur_gender else ("Menswear" if "Men" in cur_gender else "Gender-Neutral")

        gender_idx = gender_options.index(cur_gender)
        
        edit_gender = st.selectbox(
            "Tailoring Direction", 
            options=gender_options, 
            index=gender_idx,
            key=f"edit_gender_{current_user_id}"
        )
        
        edit_style = st.text_input(
            "Default Vibe", 
            value=current_profile.get("default_style", ""),
            placeholder="e.g. Modern Minimalist, sharp casual",
            key=f"edit_style_{current_user_id}"
        )

        st.write("")
        if st.button("💾 Save Profile", use_container_width=True, type="primary", key=f"btn_save_{current_user_id}"):
            if edit_name.strip():
                rename_profile(current_user_id, edit_name, edit_gender, edit_style)
                st.success("Profile updated.")
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("Name cannot be empty.")

        st.markdown("---")
        st.markdown("<span style='color: #c53030; font-size: 0.82rem; font-weight: 600;'>Danger Zone</span>", unsafe_allow_html=True)
        
        confirm_del = st.checkbox(
            f"Delete '{current_profile.get('name')}' & catalog", 
            key=f"conf_del_{current_user_id}"
        )
        
        if st.button("🗑️ Delete Profile", use_container_width=True, disabled=not confirm_del, key=f"btn_del_{current_user_id}"):
            delete_profile(current_user_id)
            remaining_keys = [k for k in load_profiles().keys() if k != current_user_id]
            
            if remaining_keys:
                st.session_state["active_user_id"] = remaining_keys[0]
                st.query_params["user"] = remaining_keys[0]
            else:
                st.session_state["active_user_id"] = None
                st.query_params.clear()

            st.success("Profile deleted.")
            time.sleep(0.4)
            st.rerun()

    # --- STORAGE MAINTENANCE ---
    with st.expander("🧹 Admin Maintenance", expanded=False):
        st.caption("Clean up orphaned images in cloud storage that are no longer linked to any garment.")
        
        if st.button("Purge Unlinked Images", use_container_width=True):
            with st.spinner("Scanning storage..."):
                res = api.purge_unlinked_storage()
                if res.get("success"):
                    count = res.get("count", 0)
                    if count > 0:
                        st.success(f"Removed {count} unlinked garment file(s).")
                    else:
                        st.info("Storage is clean — no orphaned images found.")
                else:
                    st.error(f"Cleanup failed: {res.get('error')}")


# ==========================================
# --- MAIN BANNER & TABS ---
# ==========================================
st.markdown('<div class="wolo-title">✨ WoLo Wardrobe</div>', unsafe_allow_html=True)
st.markdown('<p class="wolo-tagline">Style booboos up to be the prince and princess of the hour.</p>', unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs([
    "📸 Ingest & Digitize",
    "👗 Closet Vault", 
    "✨ Styling Salon",
    "📖 The Lookbook"
])

with tab1:
    tab1_ingest.render(current_user_id, current_profile)

with tab2:
    tab2_wardrobe.render(current_user_id, current_profile)

with tab3:
    tab3_stylist.render(current_user_id, current_profile)

with tab4:
    tab4_lookbook.render(current_user_id, current_profile)