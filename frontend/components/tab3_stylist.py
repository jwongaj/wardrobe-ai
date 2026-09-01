import streamlit as st
import time
from components import api

CHIP_OPTIONS = [
    "🔥 Love silhouette",
    "🎨 Great palette",
    "👔 Too formal",
    "👟 Too casual",
    "⚡ Color clash",
    "🌦️ Weather mismatch"
]


def render(user_id: str, profile: dict):
    st.markdown("### ✨ AI Styling Salon")
    st.caption(f"Curating outfits tailored for **{profile.get('name', user_id)}**")

    # =========================================================================
    # 1. WEATHER CONTEXT & TRAVEL OVERRIDE
    # =========================================================================
    if "weather_override" not in st.session_state:
        st.session_state.weather_override = None
    if "custom_location_query" not in st.session_state:
        st.session_state.custom_location_query = ""
    if "rejected_outfit_combos" not in st.session_state:
        st.session_state.rejected_outfit_combos = []

    # Determine Weather Context
    if st.session_state.weather_override:
        weather_data = st.session_state.weather_override
    else:
        loc_param = st.session_state.custom_location_query.strip() if st.session_state.custom_location_query.strip() else None
        weather_data = api.fetch_weather(location=loc_param)

    city_name = weather_data.get("display_location") or weather_data.get("city", "Current Location")
    temp_c = weather_data.get("temperature_c", 21.0)
    feels_like = weather_data.get("feels_like_c", temp_c)
    cond = weather_data.get("condition", "Pleasant")
    is_rain = weather_data.get("is_raining", False)

    # Minimalist Modern Weather Header
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #1F2A21 0%, #151D16 100%);
            border: 1px solid #364939;
            border-radius: 14px;
            padding: 16px 22px;
            color: #FFFFFF;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
            margin-bottom: 16px;
        ">
            <div>
                <div style="font-size: 12px; color: #9EBD8F; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 2px;">
                    📍 {city_name} {'• MANUAL OVERRIDE' if st.session_state.weather_override else '• LIVE LOCATION'}
                </div>
                <div style="font-size: 26px; font-weight: 700; letter-spacing: -0.5px;">
                    {int(temp_c)}°C <span style="font-size: 14px; font-weight: 400; color: #C2D5BD;">(feels {int(feels_like)}°C)</span>
                </div>
                <div style="font-size: 13px; color: #D8E6D4; margin-top: 2px;">
                    {cond} {'• 🌧️ Rain likely' if is_rain else ''}
                </div>
            </div>
            <div style="font-size: 34px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));">
                {'🌧️' if is_rain else '🌤️'}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Travel / Climate Expander
    with st.expander("✈️ Traveling or Override Climate", expanded=False):
        c_city1, c_city2, c_city3 = st.columns([2.5, 1.2, 1.5])
        with c_city1:
            city_input = st.text_input("Destination City / Country", value=st.session_state.custom_location_query, placeholder="e.g. Paris, Tokyo, London")
        with c_city2:
            st.write("&nbsp;")
            if st.button("Search City", use_container_width=True):
                st.session_state.custom_location_query = city_input
                st.session_state.weather_override = None
                st.rerun()
        with c_city3:
            st.write("&nbsp;")
            if st.button("↺ Reset Location", use_container_width=True, help="Reset to auto-detected local device location"):
                st.session_state.custom_location_query = ""
                st.session_state.weather_override = None
                st.toast("Reset to device location!", icon="📍")
                st.rerun()

        st.markdown("**Manual Weather Context Sliders:**")
        m1, m2, m3 = st.columns(3)
        with m1:
            man_temp = st.slider("Temperature (°C)", -5, 45, int(temp_c))
        with m2:
            man_cond = st.selectbox("Sky Condition", ["Sunny / Clear", "Partly Cloudy", "Overcast", "Windy", "Rainy"])
        with m3:
            man_rain = st.checkbox("Rain Expected", value=is_rain)

        if st.button("Apply Climate Override", type="secondary"):
            st.session_state.weather_override = {
                "display_location": city_name if city_name != "Current Location" else "Custom Climate",
                "city": city_name,
                "temperature_c": float(man_temp),
                "feels_like_c": float(man_temp),
                "condition": man_cond,
                "is_raining": man_rain
            }
            st.toast("Applied climate override!", icon="🌤️")
            st.rerun()

    st.markdown("---")

    # =========================================================================
    # 2. STYLING INPUTS
    # =========================================================================
    items = api.get_clothing_items(user_id)
    if len(items) < 2:
        st.warning("You need at least 2 pieces in your wardrobe vault. Head to **Tab 1** to ingest your garments.")
        return

    col1, col2 = st.columns(2)
    with col1:
        event = st.text_input("Occasion / Destination", value="Weekend brunch & coastal walk")
        time_of_day = st.selectbox("Time of Day", ["Daytime", "Evening", "Late Night", "All Day"])

    with col2:
        desired_vibe = st.text_input("Desired Vibe / Mood", value=profile.get("default_style", "Luminous Minimalist"))

    if st.button("✨ Style Ensemble", type="primary", use_container_width=True):
        with st.spinner("Curating ensemble with climate & taste memory..."):
            curation = api.curate_outfit(
                user_id=user_id,
                user_gender=profile.get("gender", "Womenswear"),
                event_description=event,
                time_of_day=time_of_day,
                desired_vibe=desired_vibe,
                weather=weather_data,
                available_items=items
            )

            if "error" in curation:
                st.error(f"Styling error: {curation['error']}")
                return

            st.session_state["active_curation"] = curation
            st.session_state["curation_event"] = event
            st.session_state["curation_time_of_day"] = time_of_day
            st.session_state["curation_desired_vibe"] = desired_vibe
            st.rerun()

    # =========================================================================
    # 3. CURATED LOOK & INSTANT SAVE
    # =========================================================================
    if "active_curation" in st.session_state:
        curation = st.session_state["active_curation"]
        raw_name = curation.get("outfit_name") or curation.get("title", "Curated Ensemble")
        outfit_name = raw_name.replace("🥂", "").replace("✨", "").strip()
        selected_ids = [str(x) for x in curation.get("selected_item_ids", [])]

        st.markdown(f"#### {outfit_name}")

        styling_reasoning = curation.get("styling_reasoning") or curation.get("rationale", "")
        weather_alignment = curation.get("weather_alignment", "")

        st.markdown(
            f"""
            <div style="background: #253322; border-left: 4px solid #DFB15B; padding: 14px 18px; border-radius: 8px; color: #F0F4EC; margin-bottom: 16px;">
                <p style="margin: 0 0 6px 0; font-size: 0.95rem; line-height: 1.5;"><strong>Stylist Rationale:</strong> {styling_reasoning}</p>
                {f'<p style="margin: 0; font-size: 0.88rem; color: #D1DCC9;"><strong>Weather Suitability:</strong> {weather_alignment}</p>' if weather_alignment else ''}
            </div>
            """,
            unsafe_allow_html=True
        )

        matched_items = [
            it for it in items
            if str(it.get("id")) in selected_ids or str(it.get("db_id")) in selected_ids
        ]
        if not matched_items and "items" in curation:
            matched_items = curation["items"]

        if matched_items:
            m_cols = st.columns(len(matched_items))
            for i, it in enumerate(matched_items):
                with m_cols[i]:
                    with st.container(border=True):
                        img_url = it.get("image_url", "")
                        sub_title = it.get("sub_type", "Garment")
                        if img_url:
                            try:
                                st.image(img_url, use_container_width=True)
                            except Exception:
                                st.image(f"https://placehold.co/140x140/F4F6F0/7D9D64?text={sub_title.replace(' ', '+')}", use_container_width=True)
                        else:
                            st.image(f"https://placehold.co/140x140/F4F6F0/7D9D64?text={sub_title.replace(' ', '+')}", use_container_width=True)
                        st.markdown(f"**{sub_title}**")
                        st.caption(f"{it.get('primary_color', 'Neutral')} • {it.get('fabric_material', 'Fabric')}")

        st.write("")
        if st.button("🔖 Save Look to Lookbook", type="primary", use_container_width=True):
            save_payload = {
                "user_id": user_id,
                "title": outfit_name,
                "items": matched_items,
                "item_ids": [it.get("id") or it.get("db_id") for it in matched_items],
                "occasion": st.session_state.get("curation_event", "Everyday"),
                "rationale": styling_reasoning,
                "image_url": matched_items[0].get("image_url") if matched_items else ""
            }
            if api.save_look(save_payload):
                st.toast("Ensemble saved to your Lookbook (Tab 4)!", icon="🔖")
            else:
                st.error("Failed to save to database. Please check Supabase connection.")

        # Rate and Auto-Regenerate Feedback Bar
        st.write("")
        with st.container(border=True):
            st.markdown("##### 💬 Rate this Ensemble")
            fb_col1, fb_col2 = st.columns([1.2, 3])
            with fb_col1:
                e1, e2 = st.columns(2)
                with e1:
                    if st.button("👍", help="Love this look", use_container_width=True, key="thumb_up_btn"):
                        api.submit_binary_feedback(
                            user_id=user_id,
                            rating="thumbs_up",
                            chips=st.session_state.get("stylist_chips_selected", []),
                            outfit_items=matched_items,
                            outfit_id=curation.get("id")
                        )
                        st.toast("Feedback recorded! Algorithm adjusted.", icon="👍")
                with e2:
                    if st.button("👎", help="Not for me - auto-generate new styling", use_container_width=True, key="thumb_down_btn"):
                        # 1. Submit negative feedback
                        api.submit_binary_feedback(
                            user_id=user_id,
                            rating="thumbs_down",
                            chips=st.session_state.get("stylist_chips_selected", []),
                            outfit_items=matched_items,
                            outfit_id=curation.get("id")
                        )
                        # 2. Record rejected item IDs
                        rejected_ids = [it.get("id") or it.get("db_id") for it in matched_items]
                        st.session_state.rejected_outfit_combos.append(rejected_ids)

                        # 3. Auto-regenerate fresh look
                        with st.spinner("Refining style algorithm and styling an alternative look..."):
                            new_curation = api.curate_outfit(
                                user_id=user_id,
                                user_gender=profile.get("gender", "Womenswear"),
                                event_description=st.session_state.get("curation_event", event),
                                time_of_day=st.session_state.get("curation_time_of_day", time_of_day),
                                desired_vibe=st.session_state.get("curation_desired_vibe", desired_vibe),
                                weather=weather_data,
                                available_items=items
                            )
                            if "error" not in new_curation:
                                st.session_state["active_curation"] = new_curation
                                st.toast("New ensemble styled!", icon="✨")
                                time.sleep(0.3)
                                st.rerun()
                            else:
                                st.error(f"Regeneration error: {new_curation['error']}")

            with fb_col2:
                st.pills("Reaction Tags", CHIP_OPTIONS, selection_mode="multi", label_visibility="collapsed", key="stylist_chips_selected")