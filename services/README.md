# Services Module

This directory contains business logic services for the Grovi application.

## Services

### 🌍 `gee_service.py` - Google Earth Engine Service

**Purpose:** Interface with Google Earth Engine API for satellite data processing

**Key Features:**

- Vegetation Index calculations (NDVI, EVI, GNDVI, NDWI, SAVI, VCI)
- Satellite image retrieval (Sentinel-2)
- Cloud masking
- Time series data generation

**Usage:**

```python
from services import gee_service

# Calculate NDVI for a field
result = gee_service.calculate_vi(
    geometry=field_geometry,
    vi_type="NDVI",
    start_date="2024-01-01",
    end_date="2024-12-31"
)
```

---

### 📍 `geocoding_service.py` - Geocoding Service

**Purpose:** Reverse geocoding to get addresses from coordinates

**Key Features:**

- Convert lat/lng to Thai addresses
- Uses Nominatim API
- Caching support

**Usage:**

```python
from services import geocoding_service

# Get address from coordinates
address = geocoding_service.reverse_geocode(
    lat=18.8639,
    lng=99.1296
)
```

---

### 🖼️ `image_service.py` - Image Service

**Purpose:** Handle image processing and Base64 conversion

**Key Features:**

- Convert images to Base64 data URLs
- Download images from URLs
- No file system storage (database-only)

**Usage:**

```python
from services import image_service

# Convert URL to Base64
base64_url = image_service.save_url_image(image_url)

# Process Base64 data
base64_url = image_service.save_base64_image(base64_data)
```

---

## Import Pattern

All services are exported from `services/__init__.py`:

```python
# Clean import
from services import gee_service, geocoding_service, image_service

# Or individual
from services import gee_service
```

## Dependencies

Services may depend on:

- `config.py` - Application configuration
- `models.py` - Database models
- Each other (e.g., `gee_service` uses `image_service`)
