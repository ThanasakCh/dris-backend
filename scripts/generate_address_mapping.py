"""
Script to convert source-data.csv to JSON mapping for EN↔TH address lookup.
Run this script once to generate the JSON file.
"""
import csv
import json
from pathlib import Path

def convert_csv_to_json():
    # Paths
    csv_path = Path(__file__).parent.parent.parent / "dris-frontend" / "source-data.csv"
    output_path = Path(__file__).parent.parent / "data" / "thailand_address_mapping.json"
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Mappings
    provinces = {}  # EN -> TH (clean, without prefix)
    districts = {}  # EN -> TH (clean, without prefix)
    subdistricts = {}  # EN -> TH (clean, without prefix)
    
    # Read CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Province mapping
            changwat_en = row.get('CHANGWAT_E', '').strip()
            changwat_th = row.get('CHANGWAT_T', '').strip()
            if changwat_en and changwat_th:
                # Remove prefix "จ. " from Thai name
                changwat_th_clean = changwat_th.replace('จ. ', '').strip()
                if changwat_en not in provinces:
                    provinces[changwat_en] = changwat_th_clean
            
            # District mapping
            amphoe_en = row.get('AMPHOE_E', '').strip()
            amphoe_th = row.get('AMPHOE_T', '').strip()
            if amphoe_en and amphoe_th:
                # Remove prefix "อ. ", "เขต " from Thai name
                amphoe_th_clean = amphoe_th.replace('อ. ', '').replace('เขต ', '').strip()
                if amphoe_en not in districts:
                    districts[amphoe_en] = amphoe_th_clean
            
            # Subdistrict mapping
            tambon_en = row.get('TAMBON_E', '').strip()
            tambon_th = row.get('TAMBON_T', '').strip()
            if tambon_en and tambon_th:
                # Remove prefix "ต. ", "แขวง " from Thai name
                tambon_th_clean = tambon_th.replace('ต. ', '').replace('แขวง ', '').strip()
                if tambon_en not in subdistricts:
                    subdistricts[tambon_en] = tambon_th_clean
    
    # Create mapping structure
    mapping = {
        "provinces": provinces,
        "districts": districts,
        "subdistricts": subdistricts
    }
    
    # Write JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Created mapping file: {output_path}")
    print(f"   - Provinces: {len(provinces)} entries")
    print(f"   - Districts: {len(districts)} entries")
    print(f"   - Subdistricts: {len(subdistricts)} entries")
    
    return mapping

if __name__ == "__main__":
    convert_csv_to_json()
