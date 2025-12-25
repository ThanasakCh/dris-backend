"""
Script to convert thai-administrative-division-full-my-sql.sql to JSON mapping.
Replaces the old CSV-based mapping with more accurate data from SQL.
"""
import re
import json
from pathlib import Path

def convert_sql_to_json():
    # Paths
    sql_path = Path(__file__).parent.parent.parent / "dris-frontend" / "thai-administrative-division-full-my-sql.sql"
    output_path = Path(__file__).parent.parent / "data" / "thailand_address_mapping.json"
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Mappings
    provinces = {}  # EN -> TH
    districts = {}  # EN -> TH
    subdistricts = {}  # EN -> TH
    
    # Read SQL file
    with open(sql_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse provinces
    # Pattern: INSERT INTO `provinces` VALUES ('1', '10', 'กรุงเทพมหานคร', 'Bangkok');
    province_pattern = r"INSERT INTO `provinces` VALUES \('(\d+)', '(\d+)', '([^']+)', '([^']+)'\);"
    for match in re.finditer(province_pattern, content):
        _, _, name_th, name_en = match.groups()
        provinces[name_en] = name_th
    
    # Parse districts
    # Pattern: INSERT INTO `districts` VALUES ('1', '1001', 'เขต พระนคร', 'Phra Nakhon', '1');
    district_pattern = r"INSERT INTO `districts` VALUES \('(\d+)', '(\d+)', '([^']+)', '([^']+)', '(\d+)'\);"
    for match in re.finditer(district_pattern, content):
        _, _, name_th, name_en, _ = match.groups()
        # Remove prefix like "เขต ", "เมือง" for cleaner matching
        name_th_clean = name_th.replace('เขต ', '').strip()
        districts[name_en] = name_th_clean
    
    # Parse subdistricts
    # Pattern: INSERT INTO `subdistricts` VALUES ('1', '100101', 'พระบรมมหาราชวัง', 'Phra Borom Maha Ratchawang', '13.751', '100.492', '1', '10200');
    # Some have null for name_in_english
    subdistrict_pattern = r"INSERT INTO `subdistricts` VALUES \('(\d+)', '(\d+)', '([^']+)', (?:'([^']+)'|null), '[^']+', '[^']+', '(\d+)', (?:'(\d+)'|null)\);"
    for match in re.finditer(subdistrict_pattern, content):
        _, _, name_th, name_en, _, _ = match.groups()
        if name_en:  # Only add if English name is not null
            subdistricts[name_en] = name_th
    
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
    convert_sql_to_json()
