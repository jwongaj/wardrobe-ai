import httpx
from typing import Dict, Any


def get_condition_label(code: int, is_day: int = 1) -> str:
    """Returns accurate weather description with day/night-aware iconography."""
    is_night = is_day == 0

    mapping = {
        0: "Clear Night 🌙" if is_night else "Clear Sky ☀️",
        1: "Mainly Clear 🌌" if is_night else "Mainly Clear 🌤️",
        2: "Partly Cloudy ☁️" if is_night else "Partly Cloudy ⛅",
        3: "Overcast ☁️",
        45: "Foggy 🌫️",
        48: "Depositing Rime Fog 🌫️",
        51: "Light Drizzle 🌦️",
        53: "Moderate Drizzle 🌧️",
        55: "Dense Drizzle 🌧️",
        61: "Slight Rain 🌧️",
        63: "Moderate Rain 🌧️",
        65: "Heavy Rain 🌧️",
        71: "Slight Snow 🌨️",
        73: "Moderate Snow 🌨️",
        75: "Heavy Snow ❄️",
        77: "Snow Grains ❄️",
        80: "Slight Showers 🌦️",
        81: "Moderate Showers 🌧️",
        82: "Violent Showers ⛈️",
        85: "Slight Snow Showers 🌨️",
        86: "Heavy Snow Showers ❄️",
        95: "Thunderstorm ⛈️",
        96: "Thunderstorm with Slight Hail ⛈️",
        99: "Thunderstorm with Heavy Hail ⛈️",
    }
    return mapping.get(code, "Clear Night 🌙" if is_night else "Clear Sky ☀️")


async def fetch_weather_data(manual_location: str = None, client_ip: str = None) -> Dict[str, Any]:
    """
    Resolves coordinates via IP auto-detection or global city lookup,
    then retrieves live meteorological metrics via Open-Meteo.
    """
    # Safe fallback coordinates (Sydney, AU)
    lat, lon = -33.8688, 151.2093
    city_name = "Sydney"
    country = "AU"
    is_auto = True

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 1. Manual City Search / Travel Override
            if manual_location and manual_location.strip():
                is_auto = False
                geo_url = (
                    f"https://geocoding-api.open-meteo.com/v1/search?"
                    f"name={manual_location.strip()}&count=1&language=en&format=json"
                )
                geo_res = await client.get(geo_url)
                geo_data = geo_res.json()

                if geo_data.get("results"):
                    res = geo_data["results"][0]
                    lat = res["latitude"]
                    lon = res["longitude"]
                    city_name = res.get("name", manual_location)
                    country = res.get("country_code", "")
            else:
                # 2. Automatic Device IP Resolution
                ip_target = (
                    f"http://ip-api.com/json/{client_ip}"
                    if client_ip and client_ip not in ["127.0.0.1", "localhost", "::1"]
                    else "http://ip-api.com/json/"
                )
                ip_res = await client.get(ip_target)
                if ip_res.status_code == 200:
                    ip_data = ip_res.json()
                    if ip_data.get("status") == "success":
                        lat = ip_data.get("lat", lat)
                        lon = ip_data.get("lon", lon)
                        city_name = ip_data.get("city", "Local Device")
                        country = ip_data.get("countryCode", "")

            # 3. Live Global Forecast via Open-Meteo
            w_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,is_day"
                f"&timezone=auto"
            )
            w_res = await client.get(w_url)
            w_data = w_res.json()
            curr = w_data.get("current", {})

            temp_c = curr.get("temperature_2m", 20.0)
            feels_like = curr.get("apparent_temperature", temp_c)
            code = curr.get("weather_code", 0)
            is_day = curr.get("is_day", 1)
            precip = curr.get("precipitation", 0.0)
            wind_kmh = curr.get("wind_speed_10m", 0.0)

            # Categorical flags for stylist rules
            is_rain = precip > 0.1 or code in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99]
            condition_desc = get_condition_label(code, is_day)

            display_loc = f"{city_name}, {country}".strip(" ,")

            return {
                "city": city_name,
                "display_location": display_loc,
                "is_auto": is_auto,
                "is_day": bool(is_day),
                "temp_c": round(temp_c, 1),
                "feels_like_c": round(feels_like, 1),
                "condition": condition_desc,
                "is_raining": is_rain,
                "is_freezing": temp_c <= 7.0,
                "wind_speed_kmh": round(wind_kmh, 1),
            }

    except Exception as e:
        print(f"[WeatherService] Lookup failed: {e}")
        return {
            "city": "Sydney",
            "display_location": "Sydney, AU",
            "is_auto": is_auto,
            "is_day": False,
            "temp_c": 12.0,
            "feels_like_c": 11.0,
            "condition": "Clear Night 🌙",
            "is_raining": False,
            "is_freezing": False,
            "wind_speed_kmh": 5.0,
        }