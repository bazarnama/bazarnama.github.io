import json
import os
import urllib.request
from datetime import datetime, timezone

API_URL = "https://nerkhara.com/api/v1/latest.json"
OUTPUT_FILE = "data/prices.json"

def main():
    os.makedirs("data", exist_ok=True)

    request = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": "Bazarnama/1.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("Invalid API response")

    items = payload.get("items")

    if not isinstance(items, list) or not items:
        raise ValueError("No price items received")

    valid_items = [
        item for item in items
        if isinstance(item, dict)
        and item.get("id")
        and isinstance(item.get("price"), (int, float))
    ]

    if not valid_items:
        raise ValueError("No valid prices received")

    output = {
        "generated_utc": payload.get("generated_utc"),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "items": valid_items
    }

    temporary_file = OUTPUT_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    os.replace(temporary_file, OUTPUT_FILE)

    print(f"Successfully saved {len(valid_items)} price items.")

if __name__ == "__main__":
    main()
