#!/usr/bin/env python3
"""Verify SwitchBot data parsing for both old and new payload formats.

This script fetches recent SwitchBot data from raw_data_lake and tests
the defensive parsing logic to ensure both flat and nested formats work.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.database_manager import DatabaseManager, _extract_switchbot_value

JST = timezone(timedelta(hours=9))


def main():
    print("=" * 70)
    print("SwitchBot Payload Parsing Verification")
    print("=" * 70)
    print()
    
    try:
        db = DatabaseManager("config/secrets.yaml")
    except Exception as e:
        print(f"Error: Failed to initialize DatabaseManager: {e}")
        return 1
    
    # Fetch recent SwitchBot data (last 14 days)
    start = (datetime.now(JST) - timedelta(days=14)).isoformat()
    
    try:
        response = (
            db.supabase.table("raw_data_lake")
            .select("fetched_at, payload")
            .eq("source", "switchbot")
            .eq("category", "environment")
            .gte("fetched_at", start)
            .order("fetched_at", desc=True)
            .limit(20)
            .execute()
        )
    except Exception as e:
        print(f"Error: Failed to fetch data from Supabase: {e}")
        return 1
    
    if not response.data:
        print("No SwitchBot data found in the last 14 days.")
        return 0
    
    print(f"Found {len(response.data)} SwitchBot records\n")
    
    success_count = 0
    fail_count = 0
    
    for i, row in enumerate(response.data, 1):
        payload = row.get("payload", {})
        fetched = row.get("fetched_at", "")[:19]
        
        # Test extraction using defensive parser
        temp = _extract_switchbot_value(payload, "temperature")
        humidity = _extract_switchbot_value(payload, "humidity")
        co2 = _extract_switchbot_value(payload, "CO2")
        
        # Determine payload format
        has_body_key = "body" in payload and isinstance(payload.get("body"), dict)
        has_direct_keys = any(k in payload for k in ["temperature", "humidity", "CO2"])
        
        if has_body_key:
            format_type = "nested (legacy)"
        elif has_direct_keys:
            format_type = "flat (current)"
        else:
            format_type = "unknown"
        
        # Check if parsing succeeded
        if temp is not None or humidity is not None or co2 is not None:
            status = "✓ OK"
            success_count += 1
        else:
            status = "✗ FAIL"
            fail_count += 1
        
        print(f"[{i:2d}] {fetched} | {status}")
        print(f"     Format: {format_type}")
        print(f"     Payload keys: {list(payload.keys())}")
        print(f"     Parsed: temp={temp}°C, humidity={humidity}%, CO2={co2}ppm")
        print()
    
    print("=" * 70)
    print(f"Summary: {success_count} succeeded, {fail_count} failed")
    print("=" * 70)
    
    if fail_count > 0:
        print("\n⚠ Warning: Some records failed to parse. Check payload structure.")
        return 1
    else:
        print("\n✓ All records parsed successfully!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
