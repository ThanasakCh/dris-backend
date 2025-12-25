import requests
from typing import Optional, Tuple
import asyncio
import aiohttp
import json
from pathlib import Path

class GeocodingService:
    def __init__(self):
        """Initialize Geocoding Service with address mapping"""
        self.base_url = "https://nominatim.openstreetmap.org/reverse"
        self.mapping = self._load_mapping()
        
    def _load_mapping(self) -> dict:
        """Load EN→TH address mapping from JSON file"""
        mapping_path = Path(__file__).parent.parent / "data" / "thailand_address_mapping.json"
        try:
            if mapping_path.exists():
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                print(f"Warning: Mapping file not found at {mapping_path}")
                return {"provinces": {}, "districts": {}, "subdistricts": {}}
        except Exception as e:
            print(f"Error loading mapping: {e}")
            return {"provinces": {}, "districts": {}, "subdistricts": {}}
    
    def _normalize_name(self, name: str) -> str:
        """Normalize English name by removing common suffixes and cleaning up"""
        if not name:
            return name
        
        # Remove common suffixes
        suffixes_to_remove = [
            ' Province', ' District', ' Subdistrict', ' Municipality',
            ' City', ' Town', ' Village'
        ]
        normalized = name
        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
        
        # Remove extra spaces and normalize
        normalized = ' '.join(normalized.split())
        
        return normalized.strip()
    
    def _normalize_for_matching(self, name: str) -> str:
        """Further normalize for fuzzy matching by removing spaces and special chars"""
        if not name:
            return ""
        normalized = self._normalize_name(name)
        # Remove spaces, hyphens, apostrophes for fuzzy matching
        return normalized.lower().replace(' ', '').replace('-', '').replace("'", "")
    
    def _translate_to_thai(self, name: str, level: str) -> str:
        """Translate English name to Thai using mapping
        
        Args:
            name: English name to translate
            level: 'province', 'district', or 'subdistrict'
        
        Returns:
            Thai name if found, otherwise returns None
        """
        if not name:
            return None
        
        # Normalize the name first
        normalized = self._normalize_name(name)
        
        mapping_key = f"{level}s"  # provinces, districts, subdistricts
        if mapping_key in self.mapping:
            # Try exact match first
            if normalized in self.mapping[mapping_key]:
                print(f"[DEBUG] Exact match: {normalized} -> {self.mapping[mapping_key][normalized]}")
                return self.mapping[mapping_key][normalized]
            
            # Try case-insensitive match
            name_lower = normalized.lower()
            for en_name, th_name in self.mapping[mapping_key].items():
                if en_name.lower() == name_lower:
                    print(f"[DEBUG] Case-insensitive match: {normalized} -> {th_name}")
                    return th_name
            
            # Try to match by removing "Mueang" prefix (common for district names)
            if level == 'district' and name_lower.startswith('mueang '):
                province_part = name_lower.replace('mueang ', '')
                for en_name, th_name in self.mapping[mapping_key].items():
                    if en_name.lower() == f"mueang {province_part}":
                        print(f"[DEBUG] Mueang match: {normalized} -> {th_name}")
                        return th_name
            
            print(f"[DEBUG] No match found for: {normalized} (level: {level})")
        
        return None  # Return None if not found
        
    async def reverse_geocode(self, lat: float, lng: float) -> Tuple[Optional[str], Optional[str]]:
        """Get address from latitude/longitude coordinates
        Returns: (address_th, address_en)
        """
        try:
            params = {
                'lat': lat,
                'lon': lng,
                'format': 'json',
                'accept-language': 'en',  # Request English names
                'zoom': 14,
                'addressdetails': 1
            }
            
            headers = {
                'User-Agent': 'Rice-Field-Monitoring-System'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        address_en = self._format_english_address(data)
                        address_th = self._format_thai_address(data)
                        return (address_th, address_en)
                    else:
                        print(f"Geocoding failed with status: {response.status}")
                        return (None, None)
                        
        except Exception as e:
            print(f"Error in reverse geocoding: {e}")
            return (None, None)
    
    def _find_thai_name(self, name: str) -> tuple:
        """Try to find Thai translation in any level
        Returns: (thai_name, level) or (None, None) if not found
        """
        if not name:
            return (None, None)
        
        normalized = self._normalize_name(name)
        name_lower = normalized.lower()
        name_fuzzy = self._normalize_for_matching(name)
        
        # Try each level
        for level in ['province', 'district', 'subdistrict']:
            mapping_key = f"{level}s"
            if mapping_key in self.mapping:
                # Exact match
                if normalized in self.mapping[mapping_key]:
                    return (self.mapping[mapping_key][normalized], level)
                
                # Case-insensitive match
                for en_name, th_name in self.mapping[mapping_key].items():
                    if en_name.lower() == name_lower:
                        return (th_name, level)
                
                # Fuzzy match (remove spaces and special chars)
                for en_name, th_name in self.mapping[mapping_key].items():
                    en_fuzzy = en_name.lower().replace(' ', '').replace('-', '').replace("'", "")
                    if en_fuzzy == name_fuzzy:
                        return (th_name, level)
        
        return (None, None)
    
    def _format_thai_address(self, geocoding_data: dict) -> str:
        """Format geocoding data to Thai address format
        Matches ALL API values against ALL JSON levels"""
        try:
            address = geocoding_data.get('address', {})
            
            # Collect all possible address values from API
            all_values = []
            for key in ['suburb', 'neighbourhood', 'quarter', 'village', 'hamlet',
                       'city', 'town', 'municipality', 'county',
                       'state', 'province']:
                value = address.get(key, '')
                if value and value not in all_values:
                    all_values.append(value)
            
            print(f"[DEBUG] API values collected: {all_values}")
            
            # Try matching each value against all levels
            found = {'province': None, 'district': None, 'subdistrict': None}
            
            for value in all_values:
                th_name, level = self._find_thai_name(value)
                if th_name and level:
                    print(f"[DEBUG] Matched: {value} -> {th_name} (level: {level})")
                    if found[level] is None:
                        found[level] = th_name
                else:
                    print(f"[DEBUG] No match for: {value}")
            
            print(f"[DEBUG] Final found: {found}")
            
            # Build Thai address with correct prefixes
            components = []
            
            if found['subdistrict']:
                components.append(f"ตำบล{found['subdistrict']}")
            
            if found['district']:
                components.append(f"อำเภอ{found['district']}")
            
            if found['province']:
                if found['province'] == 'กรุงเทพมหานคร':
                    components.append('กรุงเทพมหานคร')
                else:
                    components.append(f"จังหวัด{found['province']}")
            
            if components:
                return ' '.join(components)
            
            return 'ไม่สามารถระบุตำแหน่งได้'
            
        except Exception as e:
            print(f"Error formatting Thai address: {e}")
            return 'ไม่สามารถระบุตำแหน่งได้'

    def _format_english_address(self, geocoding_data: dict) -> str:
        """Format geocoding data to English address format (direct from API)"""
        try:
            address = geocoding_data.get('address', {})
            
            components = []
            
            # Subdistrict (Tambon)
            tambon = address.get('suburb', address.get('neighbourhood', address.get('quarter', '')))
            if tambon:
                components.append(tambon)
            
            # District (Amphoe)
            amphoe = address.get('city', address.get('town', address.get('municipality', address.get('county', ''))))
            if amphoe:
                components.append(amphoe)
                
            # Province
            province = address.get('state', address.get('province', ''))
            if province:
                components.append(province)
            
            if len(components) >= 2:
                return ', '.join(components)
            
            # Fallback to display_name
            display_name = geocoding_data.get('display_name', '')
            parts = display_name.split(',')[:3]
            return ', '.join(part.strip() for part in parts)
            
        except Exception as e:
            print(f"Error formatting English address: {e}")
            return geocoding_data.get('display_name', 'Location unavailable')

    def reverse_geocode_sync(self, lat: float, lng: float) -> Tuple[Optional[str], Optional[str]]:
        """Synchronous version of reverse_geocode
        Returns: (address_th, address_en)
        """
        try:
            params = {
                'lat': lat,
                'lon': lng,
                'format': 'json',
                'accept-language': 'en',  # Request English names
                'zoom': 14,
                'addressdetails': 1
            }
            
            headers = {
                'User-Agent': 'Rice-Field-Monitoring-System'
            }
            
            response = requests.get(self.base_url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                address_en = self._format_english_address(data)
                address_th = self._format_thai_address(data)
                return (address_th, address_en)
            else:
                print(f"Geocoding failed with status: {response.status_code}")
                return (None, None)
                
        except Exception as e:
            print(f"Error in reverse geocoding: {e}")
            return (None, None)

# Global instance
geocoding_service = GeocodingService()
