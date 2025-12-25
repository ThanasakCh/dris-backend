"""
Backfill address_en for existing fields
Run this script after adding the address_en column to the database
"""
from core.database import SessionLocal
from models import Field
from services.geocoding_service import geocoding_service
import time

def backfill_address_en():
    db = SessionLocal()
    
    try:
        # Get all fields where address_en is NULL
        fields = db.query(Field).filter(Field.address_en == None).all()
        print(f"Found {len(fields)} fields without address_en")
        
        for i, field in enumerate(fields):
            print(f"[{i+1}/{len(fields)}] Processing field: {field.name}")
            
            # Get both Thai and English address
            address_th, address_en = geocoding_service.reverse_geocode_sync(
                field.centroid_lat, 
                field.centroid_lng
            )
            
            if address_en:
                field.address_en = address_en
                db.commit()
                print(f"  ✓ Updated: {address_en}")
            else:
                print(f"  ✗ Failed to get English address")
            
            # Rate limit: Nominatim allows 1 request per second
            time.sleep(1.1)
        
        print("\n✓ Backfill completed!")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    backfill_address_en()
