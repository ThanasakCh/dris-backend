import ee
import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from core.config import settings
from services.image_service import image_service
import os

class GEEService:
    def __init__(self):
        """Initialize Google Earth Engine service"""
        self.initialize_gee()
        
    def initialize_gee(self):
        """Initialize GEE with service account credentials from environment variables"""
        self.gee_available = False
        try:
            # Check for required credentials in environment
            if not settings.gee_private_key or not settings.gee_service_account_email:
                print("GEE credentials not found in environment variables")
                print("Please set GEE_PRIVATE_KEY and GEE_SERVICE_ACCOUNT_EMAIL in .env file")
                return
            
            credentials_dict = {
                "type": "service_account",
                "project_id": settings.gee_project_id,
                "private_key_id": settings.gee_private_key_id,
                "private_key": settings.gee_private_key,
                "client_email": settings.gee_service_account_email,
                "client_id": settings.gee_client_id,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{settings.gee_service_account_email.replace('@', '%40')}",
                "universe_domain": "googleapis.com"
            }
            
            # Initialize Earth Engine with service account
            credentials_json = json.dumps(credentials_dict)
            credentials = ee.ServiceAccountCredentials(
                settings.gee_service_account_email,
                key_data=credentials_json
            )
            ee.Initialize(credentials, project=settings.gee_project_id)
            ee.Number(1).getInfo()
            self.gee_available = True
            print("Google Earth Engine initialized from environment variables")
            
        except Exception as e:
            print(f"Failed to initialize GEE: {e}")
            if "Not signed up" in str(e) or "project is not registered" in str(e):
                print("GEE Project not registered or Service Account lacks permissions")
            self.gee_available = False
    
    def _find_key_file(self):
        """Deprecated: This method is no longer used as we now use environment variables"""
        print(f" _find_key_file is deprecated - using environment variables instead")
        return None
    
    def get_sentinel2_collection(self, geometry: Dict, start_date: str, end_date: str):
        """Get Sentinel-2 collection for specified geometry and date range with cloud masking"""
        try:
            if not geometry:
                raise ValueError("Geometry is required but not provided")
            
            ee_geometry = ee.Geometry(geometry)
            bounds = ee_geometry.bounds().getInfo()
            if not bounds:
                raise ValueError("Invalid geometry bounds")
            
            # Get Sentinel-2 images with cloud filtering (<30%)
            collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                         .filterBounds(ee_geometry)
                         .filterDate(start_date, end_date)
                         .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
                         .select(['B2', 'B3', 'B4', 'B8', 'B11', 'B12', 'QA60']))
            
            # Apply cloud masking using QA60 band
            def apply_cloud_mask(image):
                """Apply cloud and cirrus masking using QA60 band"""
                qa = image.select('QA60')
                qa = qa.toInt()
                cloud_bit_mask = 1 << 10
                cirrus_bit_mask = 1 << 11
                mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
                    qa.bitwiseAnd(cirrus_bit_mask).eq(0))
                return image.updateMask(mask).multiply(0.0001).copyProperties(image, ["system:time_start"])
            collection = collection.map(apply_cloud_mask)
            
            collection_size = collection.size().getInfo()
            print(f"Found {collection_size} cloud-masked images for date range {start_date} to {end_date}")
            if collection_size == 0:
                print(f"No cloud-free images found in 180 days, trying extended 1-year range...")
                from datetime import datetime, timedelta
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                start_dt = end_dt - timedelta(days=365)
                collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                             .filterBounds(ee_geometry)
                             .filterDate(start_dt.strftime('%Y-%m-%d'), end_date)
                             .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
                             .select(['B2', 'B3', 'B4', 'B8', 'B11', 'B12', 'QA60']))
                collection = collection.map(apply_cloud_mask)
                collection_size = collection.size().getInfo()
                print(f"Found {collection_size} high-quality images in extended 1-year range")
            
            return collection, ee_geometry
        except Exception as e:
            print(f"Error getting Sentinel-2 collection: {e}")
            raise
    
    def calculate_vi(self, image: ee.Image, vi_type: str) -> ee.Image:
        """Calculate vegetation index"""
        try:
            if image is None:
                raise ValueError("Image is None")
            
            if vi_type == 'NDVI':
                nir = image.select('B8')
                red = image.select('B4')
                return nir.subtract(red).divide(nir.add(red)).rename('VI')
            elif vi_type == 'EVI':
                return image.expression(
                    '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))',
                    {
                        'NIR': image.select('B8'),
                        'RED': image.select('B4'),
                        'BLUE': image.select('B2')
                    }
                ).rename('VI')
            elif vi_type == 'GNDVI':
                nir = image.select('B8')
                green = image.select('B3')
                return nir.subtract(green).divide(nir.add(green)).rename('VI')
            elif vi_type == 'NDWI':
                green = image.select('B3')
                nir = image.select('B8')
                return green.subtract(nir).divide(green.add(nir)).rename('VI')
            elif vi_type == 'SAVI':
                return image.expression(
                    '((NIR - RED) / (NIR + RED + 0.5)) * (1 + 0.5)',
                    {
                        'NIR': image.select('B8'),
                        'RED': image.select('B4')
                    }
                ).rename('VI')
            elif vi_type == 'VCI':
                nir = image.select('B8')
                red = image.select('B4')
                ndvi = nir.subtract(red).divide(nir.add(red))
                return ndvi.multiply(100).rename('VI')
            else:
                raise ValueError(f"Unknown VI type: {vi_type}")
        except Exception as e:
            print(f"Error calculating VI {vi_type}: {e}")
            raise
    
    def get_vi_statistics(self, geometry: Dict, vi_type: str, date: Optional[datetime] = None) -> Dict:
        """Get VI statistics for a field geometry"""
        if not self.gee_available:
            raise Exception("ไม่สามารถเชื่อมต่อ Google Earth Engine ได้ กรุณาติดต่อผู้ดูแลระบบ")
        
        try:
            if date is None:
                date = datetime.now()
            start_date = (date - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = (date + timedelta(days=7)).strftime('%Y-%m-%d')
            
            collection, ee_geometry = self.get_sentinel2_collection(geometry, start_date, end_date)
            collection_size = collection.size().getInfo()
            if collection_size == 0:
                raise ValueError("No suitable images found for the specified date range")
            image = collection.sort('system:time_start', False).first()
            if image is None:
                raise ValueError("Failed to get image from collection")
            try:
                image_bands = image.bandNames().getInfo()
                required_bands = ['B8', 'B4']
                if vi_type == 'EVI':
                    required_bands = ['B8', 'B4', 'B2']
                elif vi_type in ['GNDVI', 'NDWI']:
                    required_bands = ['B8', 'B3']
                
                missing_bands = [band for band in required_bands if band not in image_bands]
                if missing_bands:
                    raise ValueError(f"Image missing required bands: {missing_bands}")
                    
            except Exception as e:
                print(f"Error checking image bands: {e}")
                raise ValueError("Image bands validation failed")
            vi_image = self.calculate_vi(image, vi_type)
            if vi_image is None:
                raise ValueError("VI calculation returned null image")
            stats = vi_image.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    reducer2=ee.Reducer.minMax(),
                    sharedInputs=True
                ),
                geometry=ee_geometry,
                scale=10,
                maxPixels=1e9
            ).getInfo()
            mean_value = stats.get('VI_mean', None)
            min_value = stats.get('VI_min', None)
            max_value = stats.get('VI_max', None)
            if mean_value is None:
                raise ValueError("Failed to calculate VI statistics - no data returned")
            if vi_type not in ['NDWI'] and mean_value == 0:
                raise ValueError("Failed to calculate VI statistics - zero value detected")
            analysis_message = self.generate_analysis_message(mean_value, vi_type)
            
            return {
                'mean_value': float(mean_value),
                'min_value': float(min_value) if min_value is not None else float(mean_value),
                'max_value': float(max_value) if max_value is not None else float(mean_value),
                'analysis_message': analysis_message,
                'measurement_date': date.isoformat()
            }
            
        except Exception as e:
            print(f"Error getting VI statistics: {e}")
            raise Exception("ไม่สามารถดึงข้อมูลจากดาวเทียมได้ กรุณาลองใหม่อีกครั้ง")
    
    def generate_vi_overlay(self, geometry: Dict, vi_type: str, date: Optional[datetime] = None) -> str:
        """Generate VI overlay image as base64 data URL"""
        try:
            if date is None:
                date = datetime.now()
            
            start_date = (date - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = (date + timedelta(days=7)).strftime('%Y-%m-%d')
            
            collection, ee_geometry = self.get_sentinel2_collection(geometry, start_date, end_date)
            image = collection.sort('system:time_start', False).first()
            
            if image is None:
                print(f" No image available from GEE for overlay generation")
                return ""
            
            vi_image = self.calculate_vi(image, vi_type)
            vis_params = self.get_vis_params(vi_type)
            thumbnail_url = vi_image.getThumbURL({
                'dimensions': 512,
                'region': ee_geometry,
                'format': 'png',
                **vis_params
            })
            base64_data_url = image_service.save_url_image(thumbnail_url, f"vi_{vi_type}_{date.strftime('%Y%m%d')}")
            
            if base64_data_url:
                return base64_data_url
            else:
                return thumbnail_url
        except Exception as e:
            print(f"Error generating VI overlay: {e}")
            return ""
    
    def get_vis_params(self, vi_type: str) -> Dict:
        """Get visualization parameters for different VI types with improved color gradients"""
        vis_params = {
            'NDVI': {
                'min': -0.2, 
                'max': 0.8, 
                'palette': ['#ff0000', '#ff4500', '#ffff00', '#9acd32', '#00ff00', '#228b22', '#006400']
            },
            'EVI': {
                'min': -0.1, 
                'max': 0.7, 
                'palette': ['#8b0000', '#ff4500', '#ffff00', '#9acd32', '#00ff00', '#228b22', '#006400']
            },
            'GNDVI': {
                'min': 0, 
                'max': 0.8, 
                'palette': ['#8b0000', '#ff4500', '#ffff00', '#9acd32', '#00ff00', '#228b22', '#006400']
            },
            'NDWI': {
                'min': -0.3, 
                'max': 0.5, 
                'palette': ['#8b4513', '#daa520', '#ffff99', '#87ceeb', '#4169e1', '#000080']
            },
            'SAVI': {
                'min': -0.1, 
                'max': 0.7, 
                'palette': ['#8b0000', '#ff4500', '#ffff00', '#9acd32', '#00ff00', '#228b22', '#006400']
            },
            'VCI': {
                'min': 0, 
                'max': 100, 
                'palette': ['#8b0000', '#ff4500', '#ffff00', '#9acd32', '#00ff00', '#228b22', '#006400']
            }
        }
        return vis_params.get(vi_type, vis_params['NDVI'])
    
        
    def generate_analysis_message(self, mean_value: float, vi_type: str) -> str:
        """Generate analysis message based on VI value according to the improved classification table"""
        try:
            if vi_type == 'NDVI':
                if mean_value < 0.2:
                    return "ดินเปล่า/น้ำ - ยังไม่ปลูกหรือแปลงว่าง"
                elif 0.2 <= mean_value < 0.4:
                    return "ต้นข้าวเริ่มขึ้น - ระยะแตกกอเริ่มต้น"
                elif 0.4 <= mean_value < 0.6:
                    return "ต้นข้าวเขียวปานกลาง - ใบใบเริ่มหนาแน่น"
                else:
                    return "ต้นข้าวเขียวหนาแน่นมาก - ใบสมบูรณ์เต็มที่"
            
            elif vi_type == 'EVI':
                if mean_value < 0.2:
                    return "ยังไม่งอก - ข้าวเพิ่งปลูกหรือยังไม่ฟื้นตัว"
                elif 0.2 <= mean_value < 0.4:
                    return "ต้นกล้า - ข้าวเริ่มเขียว แตกใบ"
                elif 0.4 <= mean_value < 0.6:
                    return "เจริญเติบโต - ใบเริ่มแน่น เขียวดี"
                else:
                    return "สมบูรณ์ - ข้าวเขียวจัด ระยะออกรวง"
            
            elif vi_type == 'GNDVI':
                if mean_value < 0.3:
                    return "ขาดไนโตรเจน - ใบเหลือง ขาดความเขียว"
                elif 0.3 <= mean_value < 0.6:
                    return "ปานกลาง - ข้าวโตปกติ"
                elif 0.6 <= mean_value < 0.8:
                    return "เขียวเข้ม - ข้าวสมบูรณ์ ใบเขียวดี"
                else:
                    return "เขียวมาก - ข้าวใบแน่น ความเขียวสูง"
            
            elif vi_type == 'NDWI':
                if mean_value < 0.0:
                    return "ดินแห้ง - ความชื้นต่ำ ไม่มีน้ำขัง"
                elif 0.0 <= mean_value < 0.2:
                    return "ชื้นน้อย - เริ่มขาดน้ำ"
                elif 0.2 <= mean_value < 0.4:
                    return "ชื้นปกติ - ความชื้นพอเหมาะสำหรับข้าว"
                else:
                    return "ชุ่มน้ำ - น้ำขัง/น้ำมาก เหมาะกับข้าวระยะแรก"
            
            elif vi_type == 'VCI':
                if mean_value < 20:
                    return "เครียดจัด - พืชเสียหาย ขาดน้ำหรือธาตุอาหาร"
                elif 20 <= mean_value < 40:
                    return "เครียด - ข้าวไม่สมบูรณ์ ใบเหลือง"
                elif 40 <= mean_value < 60:
                    return "ปานกลาง - ข้าวโตได้ปกติ"
                elif 60 <= mean_value < 80:
                    return "ค่อนข้างดี - ใบเขียว สภาพดี"
                else:
                    return "ดีมาก - เขียวจัด สมบูรณ์เต็มที่"
            
            elif vi_type == 'SAVI':
                if mean_value < 0.2:
                    return "ดินเปล่า - พืชไม่ปกคลุมดิน"
                elif 0.2 <= mean_value < 0.4:
                    return "เริ่มปกคลุม - ข้าวโตเริ่มบังดิน"
                elif 0.4 <= mean_value < 0.6:
                    return "ปานกลาง - ข้าวเขียวและปกคลุมดี"
                else:
                    return "เขียวจัด - ข้าวเขียวหนาแน่นมาก"
                    
            else:
                return f"ค่าเฉลี่ย {vi_type}: {mean_value:.3f}"
                
        except Exception as e:
            print(f"Error generating analysis message: {e}")
            return "ไม่สามารถวิเคราะห์ได้"
    
    def get_latest_images_data(self, geometry: Dict, vi_type: str, limit: int = 4) -> List[Dict]:
        """Get the latest real images with VI data from Google Earth Engine"""
        print(f" Fetching real satellite data from GEE for {vi_type}")
        if not self.gee_available:
            print(f" Google Earth Engine ไม่พร้อมใช้งาน")
            raise Exception("ไม่สามารถเชื่อมต่อ Google Earth Engine ได้ กรุณาติดต่อผู้ดูแลระบบ")
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=180)
            
            print(f" Searching for images between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}")
            
            collection, ee_geometry = self.get_sentinel2_collection(
                geometry, 
                start_date.strftime('%Y-%m-%d'), 
                end_date.strftime('%Y-%m-%d')
            )
            def mask_clouds(image):
                qa = image.select('QA60')
                qa = qa.toInt()
                
                cloud_bit_mask = 1 << 10
                cirrus_bit_mask = 1 << 11
                mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
                    qa.bitwiseAnd(cirrus_bit_mask).eq(0))
                
                return image.updateMask(mask).copyProperties(image, ["system:time_start"])
            try:
                collection = collection.map(mask_clouds)
            except Exception as e:
                print(f"Cloud masking failed, using original collection: {e}")
            total_images_before = collection.size().getInfo()
            print(f" Found {total_images_before} cloud-masked images")
            
            if total_images_before == 0:
                print(f" No cloud-free images found in the specified date range")
                return []
            collection = collection.sort('system:time_start', False)
            image_list = collection.toList(collection.size())
            total_images = image_list.size().getInfo()
            
            print(f" Processing {total_images} images to find {limit} unique dates")
            
            images_data = []
            used_dates = set()
            max_attempts = min(total_images, limit * 5)
            for i in range(max_attempts):
                if len(images_data) >= limit:
                    break
                    
                try:
                    image = ee.Image(image_list.get(i))
                    date_millis = image.get('system:time_start').getInfo()
                    acquisition_date = datetime.fromtimestamp(date_millis / 1000)
                    date_key = acquisition_date.strftime('%Y-%m-%d')
                    if date_key in used_dates:
                        print(f" Skipping duplicate date: {date_key}")
                        continue
                    if used_dates:
                        min_gap_found = True
                        for existing_date_str in used_dates:
                            existing_date = datetime.strptime(existing_date_str, '%Y-%m-%d')
                            gap_days = abs((acquisition_date - existing_date).days)
                            if gap_days < 5:
                                print(f" Skipping date {date_key} - too close to {existing_date_str} (gap: {gap_days} days)")
                                min_gap_found = False
                                break
                        
                        if not min_gap_found:
                            continue
                    vi_image = self.calculate_vi(image, vi_type)
                    stats = vi_image.reduceRegion(
                        reducer=ee.Reducer.mean().combine(
                            reducer2=ee.Reducer.minMax(),
                            sharedInputs=True
                        ),
                        geometry=ee_geometry,
                        scale=10,
                        maxPixels=1e9
                    ).getInfo()
                    
                    mean_value = stats.get('VI_mean', 0)
                    min_value = stats.get('VI_min', 0)
                    max_value = stats.get('VI_max', 0)
                    if mean_value is not None and (vi_type == 'NDWI' or mean_value != 0):
                        vis_params = self.get_vis_params(vi_type)
                        
                        try:
                            clipped_vi = vi_image.clip(ee_geometry)
                            visualized_vi = clipped_vi.visualize(**vis_params)
                            
                            thumbnail_url = visualized_vi.getThumbURL({
                                'dimensions': 512,
                                'region': ee_geometry,
                                'format': 'png'
                            })
                            overlay_url = image_service.save_url_image(
                                thumbnail_url, 
                                f"vi_{vi_type}_{acquisition_date.strftime('%Y%m%d_%H%M%S')}"
                            )
                            
                            if not overlay_url:
                                overlay_url = thumbnail_url
                        except Exception as overlay_error:
                            print(f" Overlay generation failed for {date_key}: {overlay_error}")
                            print(f" Skipping image for {date_key} - cannot generate real overlay")
                            continue
                        
                        images_data.append({
                            'acquisition_date': acquisition_date.isoformat(),
                            'mean_value': float(mean_value),
                            'min_value': float(min_value) if min_value else float(mean_value),
                            'max_value': float(max_value) if max_value else float(mean_value),
                            'overlay_url': overlay_url,
                            'analysis_message': self.generate_analysis_message(mean_value, vi_type)
                        })
                        used_dates.add(date_key)
                        print(f" Added real GEE image for date: {date_key}, VI: {mean_value:.3f}")
                        
                except Exception as e:
                    print(f" Error processing image {i}: {e}")
                    continue
            
            print(f" Successfully retrieved {len(images_data)} real satellite images from {total_images} available")
            
            if len(images_data) == 0:
                print(f" No valid VI images could be processed from GEE")
                return []
            images_data.sort(key=lambda x: x['acquisition_date'], reverse=True)
            
            return images_data
            
        except Exception as e:
            print(f" Critical error accessing Google Earth Engine: {e}")
            print(f" Please check:")
            print(f"   1. GEE service account key file exists")
            print(f"   2. GEE authentication is working")
            print(f"   3. Internet connection is available")
            return []

    def get_timeseries_data(self, geometry: Dict, vi_type: str, 
                           start_date: datetime, end_date: datetime, analysis_type: str = None) -> List[Dict]:
        """Get time series data for VI analysis - Monthly/Yearly averages only"""
        try:
            print(f" GEE: Getting {vi_type} timeseries from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            print(f" Analysis type: {analysis_type}")
            
            collection, ee_geometry = self.get_sentinel2_collection(
                geometry, 
                start_date.strftime('%Y-%m-%d'), 
                end_date.strftime('%Y-%m-%d')
            )
            image_count = collection.size().getInfo()
            print(f" Found {image_count} Sentinel-2 images in date range")
            
            if image_count == 0:
                print(f" No images found in the specified date range")
                return []
            
            timeseries_data = []
            if analysis_type == 'ten_year_avg':
                timeseries_data = self._calculate_yearly_averages(collection, ee_geometry, vi_type, start_date, end_date)
            else:
                timeseries_data = self._calculate_monthly_averages(collection, ee_geometry, vi_type, start_date, end_date)
            
            print(f" Successfully processed {len(timeseries_data)} data points")
            return timeseries_data
            
        except Exception as e:
            print(f" Error getting timeseries data: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _calculate_yearly_averages(self, collection, ee_geometry, vi_type: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Calculate yearly averages for 10-year analysis"""
        yearly_data = []
        
        current_year = start_date.year
        end_year = end_date.year
        
        while current_year <= end_year:
            try:
                print(f" Processing year {current_year}")
                year_start = f"{current_year}-01-01"
                year_end = f"{current_year}-12-31"
                yearly_collection = collection.filterDate(year_start, year_end)
                yearly_count = yearly_collection.size().getInfo()
                
                if yearly_count > 0:
                    print(f"   Found {yearly_count} images in {current_year}")
                    yearly_vi = yearly_collection.map(lambda img: self.calculate_vi(img, vi_type))
                    yearly_mean = yearly_vi.mean()
                    stats = yearly_mean.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=ee_geometry,
                        scale=10,
                        maxPixels=1e9
                    ).getInfo()
                    
                    vi_value = stats.get('VI')
                    
                    if vi_value is not None and vi_value > 0:
                        yearly_data.append({
                            'date': datetime(current_year, 1, 1).isoformat(),
                            'value': float(vi_value)
                        })
                        print(f"    {current_year}: {vi_value:.3f}")
                    else:
                        print(f"    {current_year}: No valid data")
                else:
                    print(f"    {current_year}: No images available")
                    
            except Exception as e:
                print(f"    Error processing year {current_year}: {e}")
            
            current_year += 1
        
        return yearly_data

    def _calculate_monthly_averages(self, collection, ee_geometry, vi_type: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Calculate monthly averages for monthly/yearly analysis"""
        monthly_data = []
        
        current_date = datetime(start_date.year, start_date.month, 1)
        end_month = datetime(end_date.year, end_date.month, 1)
        
        while current_date <= end_month:
            try:
                month_start = current_date.strftime('%Y-%m-01')
                if current_date.month == 12:
                    next_month = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    next_month = current_date.replace(month=current_date.month + 1)
                month_end = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
                
                print(f" Processing {current_date.strftime('%B %Y')} ({month_start} to {month_end})")
                monthly_collection = collection.filterDate(month_start, month_end)
                monthly_count = monthly_collection.size().getInfo()
                
                if monthly_count > 0:
                    print(f"   Found {monthly_count} images in {current_date.strftime('%B %Y')}")
                    monthly_vi = monthly_collection.map(lambda img: self.calculate_vi(img, vi_type))
                    monthly_mean = monthly_vi.mean()
                    stats = monthly_mean.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=ee_geometry,
                        scale=10,
                        maxPixels=1e9
                    ).getInfo()
                    
                    vi_value = stats.get('VI')
                    
                    if vi_value is not None and vi_value > 0:
                        monthly_data.append({
                            'date': current_date.isoformat(),
                            'value': float(vi_value)
                        })
                        print(f"    {current_date.strftime('%B %Y')}: {vi_value:.3f}")
                    else:
                        print(f"    {current_date.strftime('%B %Y')}: No valid data")
                else:
                    print(f"    {current_date.strftime('%B %Y')}: No images available")
                
            except Exception as e:
                print(f"    Error processing {current_date.strftime('%B %Y')}: {e}")
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        return monthly_data
gee_service = GEEService()
