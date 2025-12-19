from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from schemas import GeocodeResponse, SearchLocationRequest, SearchLocationResponse
import httpx
import asyncio

router = APIRouter(prefix="/utils", tags=["utilities"])

@router.get("/geocode/reverse")
async def reverse_geocode(lat: float, lng: float) -> GeocodeResponse:
    """Reverse geocoding to get address from coordinates"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "format": "json",
                    "lat": lat,
                    "lon": lng,
                    "zoom": 14,
                    "addressdetails": 1,
                    "countrycodes": "th"
                },
                headers={"User-Agent": "Grovi-CropMonitoring/1.0"}
            )
            
            if response.status_code == 200:
                data = response.json()
                address = data.get("display_name", f"พิกัด {lat:.6f}, {lng:.6f}")
                
                return GeocodeResponse(
                    address=address,
                    lat=lat,
                    lng=lng
                )
            else:
                return GeocodeResponse(
                    address=f"พิกัด {lat:.6f}, {lng:.6f}",
                    lat=lat,
                    lng=lng
                )
                
    except Exception as e:
        print(f"Reverse geocoding error: {e}")
        return GeocodeResponse(
            address=f"พิกัด {lat:.6f}, {lng:.6f}",
            lat=lat,
            lng=lng
        )

@router.get("/search")
async def search_locations(q: str, limit: int = 8) -> SearchLocationResponse:
    """Search for locations using Nominatim"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "format": "json",
                    "countrycodes": "th",
                    "q": q,
                    "limit": limit,
                    "addressdetails": 1
                },
                headers={"User-Agent": "Grovi-CropMonitoring/1.0"}
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for item in data:
                    results.append({
                        "display_name": item.get("display_name", ""),
                        "lat": float(item.get("lat", 0)),
                        "lon": float(item.get("lon", 0)),
                        "type": item.get("type", ""),
                        "class": item.get("class", "")
                    })
                
                return SearchLocationResponse(results=results)
            else:
                return SearchLocationResponse(results=[])
                
    except Exception as e:
        print(f"Location search error: {e}")
        return SearchLocationResponse(results=[])

@router.get("/area/thai-format")
def convert_area_to_thai(area_m2: float) -> Dict[str, Any]:
    """Convert area in square meters to Thai units (rai, ngan, wah)"""
    try:
        # 1 ไร่ = 1600 ตร.ม. | 1 งาน = 400 ตร.ม. | 1 ตร.วา = 4 ตร.ม.
        rai = int(area_m2 // 1600)
        rem1 = area_m2 - rai * 1600
        ngan = int(rem1 // 400)
        rem2 = rem1 - ngan * 400
        wah = round(rem2 / 4)
        
        thai_format = f"{rai} ไร่ {ngan} งาน {wah} ตร.วา"
        
        return {
            "area_m2": area_m2,
            "rai": rai,
            "ngan": ngan,
            "wah": wah,
            "thai_format": thai_format
        }
        
    except Exception as e:
        print(f"Area conversion error: {e}")
        return {
            "area_m2": area_m2,
            "rai": 0,
            "ngan": 0,
            "wah": 0,
            "thai_format": "0 ไร่ 0 งาน 0 ตร.วา"
        }

@router.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "Grovi API is running",
        "version": "1.0.0"
    }

@router.get("/vi-types")
def get_available_vi_types():
    """Get list of available vegetation indices"""
    return {
        "vi_types": [
            {
                "code": "NDVI",
                "name": "Normalized Difference Vegetation Index",
                "name_th": "ดัชนีพืชพรรณแบบปกติ",
                "range": [0, 1],
                "description": "ใช้วัดความหนาแน่นของพืชพรรณ"
            },
            {
                "code": "EVI",
                "name": "Enhanced Vegetation Index",
                "name_th": "ดัชนีพืชพรรณแบบปรับปรุง",
                "range": [0, 1],
                "description": "ดัชนีพืชพรรณที่ปรับปรุงแล้ว ลดผลกระทบจากบรรยากาศ"
            },
            {
                "code": "GNDVI",
                "name": "Green Normalized Difference Vegetation Index",
                "name_th": "ดัชนีพืชพรรณสีเขียว",
                "range": [0, 1],
                "description": "เน้นการวัดพืชพรรณในช่วงแสงสีเขียว"
            },
            {
                "code": "NDWI",
                "name": "Normalized Difference Water Index",
                "name_th": "ดัชนีน้ำแบบปกติ",
                "range": [-1, 1],
                "description": "ใช้วัดความชื้นในดินและพืช"
            },
            {
                "code": "SAVI",
                "name": "Soil Adjusted Vegetation Index",
                "name_th": "ดัชนีพืชพรรณปรับดิน",
                "range": [0, 1],
                "description": "ดัชนีพืชพรรณที่ปรับผลกระทบจากดิน"
            },
            {
                "code": "VCI",
                "name": "Vegetation Condition Index",
                "name_th": "ดัชนีสภาพพืชพรรณ",
                "range": [0, 100],
                "description": "วัดสภาพพืชพรรณเปรียบเทียบกับค่าประวัติศาสตร์"
            }
        ]
    }
