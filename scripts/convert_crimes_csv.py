#!/usr/bin/env python3
"""
Convert Chicago crime CSV data to JSON format.

Reads crime data from CSV and converts to JSON with the following fields:
- primary_type → type
- latitude → lat (float)
- longitude → lon (float)
- date

Ignores rows with missing coordinates and limits to 500 records.
"""

import csv
import json
import sys
from pathlib import Path


def convert_crimes_csv_to_json(
    csv_file: Path,
    json_file: Path,
    limit: int = 500
) -> int:
    """
    Convert Chicago crime CSV to JSON.
    
    Args:
        csv_file: Path to input CSV file
        json_file: Path to output JSON file
        limit: Maximum number of records to include (default: 500)
    
    Returns:
        Number of records written
    """
    if not csv_file.exists():
        print(f"Error: CSV file not found: {csv_file}")
        return 0
    
    crimes = []
    skipped = 0
    
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            if reader.fieldnames is None:
                print("Error: CSV file is empty or invalid")
                return 0
            
            print(f"CSV fields: {reader.fieldnames}")
            
            for row_num, row in enumerate(reader, start=1):
                if len(crimes) >= limit:
                    print(f"Reached limit of {limit} records")
                    break
                
                # Extract and validate required fields
                try:
                    # Handle variations in column names (with/without spaces)
                    latitude_str = row.get("LATITUDE", "").strip()
                    longitude_str = row.get("LONGITUDE", "").strip()
                    
                    if not latitude_str or not longitude_str:
                        skipped += 1
                        continue
                    
                    latitude = float(latitude_str)
                    longitude = float(longitude_str)
                    
                    # Skip rows with invalid coordinates (0, 0 or None)
                    if latitude == 0 or longitude == 0:
                        skipped += 1
                        continue
                    
                    # Get primary type - handle column name variations
                    primary_type = row.get(" PRIMARY DESCRIPTION") or row.get("PRIMARY DESCRIPTION", "Unknown")
                    primary_type = primary_type.strip()
                    
                    # Get date
                    date_str = row.get("DATE  OF OCCURRENCE") or row.get("DATE OF OCCURRENCE", "")
                    date_str = date_str.strip()
                    
                    crime_record = {
                        "type": primary_type,
                        "lat": latitude,
                        "lon": longitude,
                        "date": date_str
                    }
                    
                    crimes.append(crime_record)
                
                except (ValueError, TypeError) as e:
                    skipped += 1
                    continue
                
                if row_num % 100 == 0:
                    print(f"Processed {row_num} rows, collected {len(crimes)} valid records")
    
    except Exception as e:
        print(f"Error reading CSV: {str(e)}")
        return 0
    
    # Write JSON file
    try:
        json_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(crimes, f, indent=2)
        
        print(f"\nSuccessfully wrote {len(crimes)} records to {json_file}")
        print(f"Skipped {skipped} records with missing coordinates")
        
        return len(crimes)
    
    except Exception as e:
        print(f"Error writing JSON: {str(e)}")
        return 0


def main():
    """Main entry point."""
    # Determine file paths
    project_root = Path(__file__).parent.parent
    csv_path = project_root / "server" / "data" / "Crimes_-_One_year_prior_to_present_20260401.csv"
    json_path = project_root / "server" / "data" / "crimes.json"
    
    # Check if CSV exists
    if not csv_path.exists():
        print(f"Error: CSV not found at {csv_path}")
        print("\nUsage: python scripts/convert_crimes_csv.py [csv_path] [json_path]")
        sys.exit(1)
    
    print(f"Converting CSV to JSON...")
    print(f"Input: {csv_path}")
    print(f"Output: {json_path}")
    print()
    
    count = convert_crimes_csv_to_json(csv_path, json_path)
    
    if count > 0:
        print(f"\n✅ Conversion complete!")
        sys.exit(0)
    else:
        print(f"\n❌ Conversion failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
