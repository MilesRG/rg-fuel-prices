"""
fetch_prices.py
Fetches fuel prices for the RG region from the CheckFuelPrices API
and saves them to data/stations.json for use by the static website.

Runs via GitHub Actions on a daily schedule.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# RG region representative postcode centres
# Each covers a ~3 mile radius, so we pick enough centres
# to give comprehensive coverage across the whole RG area
POSTCODES = [
    ("RG1",  51.4543, -0.9781),   # Reading central
    ("RG4",  51.4717, -0.9631),   # Caversham
    ("RG6",  51.4490, -0.9410),   # Earley
    ("RG2",  51.4295, -0.9762),   # Reading south
    ("RG30", 51.4540, -1.0051),   # Tilehurst
    ("RG7",  51.3900, -1.0700),   # Mortimer
    ("RG8",  51.5200, -1.1000),   # Pangbourne / Goring
    ("RG9",  51.5360, -0.9010),   # Henley-on-Thames
    ("RG10", 51.4760, -0.8720),   # Twyford
    ("RG14", 51.3950, -1.3230),   # Newbury
    ("RG18", 51.4220, -1.2550),   # Thatcham
    ("RG21", 51.2640, -1.0870),   # Basingstoke central
    ("RG22", 51.2470, -1.1040),   # Basingstoke south
    ("RG24", 51.2860, -1.0740),   # Basingstoke north
    ("RG26", 51.3310, -1.1660),   # Tadley
    ("RG27", 51.2760, -0.9690),   # Hook
    ("RG29", 51.2040, -1.0960),   # Whitchurch
    ("RG40", 51.4100, -0.8410),   # Wokingham
    ("RG42", 51.4170, -0.7520),   # Bracknell
    ("RG45", 51.3740, -0.7960),   # Crowthorne
]

FUEL_TYPES = ["E10", "B7", "E5", "SDV"]
API_BASE   = "https://checkfuelprices.co.uk/api/widget/stations"

def fetch_stations(lat, lng, fuel):
    url = f"{API_BASE}?lat={lat}&lng={lng}&fuel={fuel}"
    req = urllib.request.Request(url, headers={"User-Agent": "RGFuelPrices/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  Warning: failed to fetch {fuel} near ({lat},{lng}): {e}")
        return []

def parse_price(raw, fuel):
    if isinstance(raw, dict):
        for key in [fuel, fuel.lower(), "price"]:
            if key in raw and raw[key] is not None:
                try:
                    return float(raw[key])
                except (ValueError, TypeError):
                    pass
        if "prices" in raw and isinstance(raw["prices"], dict):
            for key in [fuel, fuel.lower()]:
                if key in raw["prices"] and raw["prices"][key] is not None:
                    try:
                        return float(raw["prices"][key])
                    except (ValueError, TypeError):
                        pass
    return None

def normalise(raw, fuel):
    """Turn a raw API station dict into our standard format."""
    lat = raw.get("lat") or raw.get("latitude") or (raw.get("location") or {}).get("lat")
    lng = raw.get("lng") or raw.get("longitude") or (raw.get("location") or {}).get("lng")
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None

    price = parse_price(raw, fuel)
    if price is None:
        return None

    brand   = (raw.get("brand") or raw.get("retailer_name") or "Independent").strip()
    name    = (raw.get("site_name") or raw.get("name") or brand).strip()
    address = ", ".join(filter(None, [
        raw.get("address") or raw.get("street_address") or raw.get("street") or "",
        raw.get("town") or raw.get("city") or "",
        raw.get("postcode") or raw.get("post_code") or "",
    ]))

    return {
        "id":       raw.get("site_id") or raw.get("id") or f"{lat:.5f},{lng:.5f}",
        "brand":    brand,
        "name":     name,
        "address":  address,
        "postcode": raw.get("postcode") or raw.get("post_code") or "",
        "lat":      lat,
        "lng":      lng,
        "prices":   {fuel: price},
    }

def main():
    print(f"Starting fetch at {datetime.now(timezone.utc).isoformat()}")
    all_stations = {}   # id -> station dict

    for (label, lat, lng) in POSTCODES:
        print(f"  Querying {label} ({lat}, {lng})...")
        for fuel in FUEL_TYPES:
            raw_list = fetch_stations(lat, lng, fuel)
            items = raw_list if isinstance(raw_list, list) else (
                raw_list.get("stations") or raw_list.get("data") or []
            )
            for raw in items:
                station = normalise(raw, fuel)
                if station is None:
                    continue
                sid = station["id"]
                if sid not in all_stations:
                    all_stations[sid] = {k: v for k, v in station.items() if k != "prices"}
                    all_stations[sid]["prices"] = {}
                all_stations[sid]["prices"].update(station["prices"])
            time.sleep(0.2)   # gentle rate limiting

    stations_list = list(all_stations.values())
    print(f"  Total unique stations found: {len(stations_list)}")

    import os
    os.makedirs("data", exist_ok=True)

    output = {
        "updated":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count":    len(stations_list),
        "stations": stations_list,
    }

    with open("data/stations.json", "w") as f:
        json.dump(output, f, separators=(",", ":"))

    print(f"  Saved {len(stations_list)} stations to data/stations.json")

if __name__ == "__main__":
    main()
