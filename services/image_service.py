import base64
import requests
from typing import Optional
from PIL import Image
from io import BytesIO

class ImageService:
    def __init__(self):
        """Initialize Image Service - No file storage needed"""
        pass
        
    def save_base64_image(self, base64_data: str, filename_prefix: str = "vi") -> str:
        """
        Process and return Base64 data URL
        
        Args:
            base64_data: Base64 string (with or without data URL prefix)
            filename_prefix: Ignored (kept for backward compatibility)
            
        Returns:
            Base64 data URL string (data:image/png;base64,...)
        """
        try:
            if not base64_data.startswith("data:image"):
                base64_data = base64_data.strip()
                base64_data = f"data:image/png;base64,{base64_data}"
            
            return base64_data
            
        except Exception as e:
            print(f"Error processing base64 image: {e}")
            return None
    
    def save_url_image(self, image_url: str, filename_prefix: str = "vi") -> Optional[str]:
        """
        Download image from URL and convert to Base64 data URL
        
        Args:
            image_url: URL of the image to download
            filename_prefix: Ignored (kept for backward compatibility)
            
        Returns:
            Base64 data URL string or None if error
        """
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            image_bytes = response.content
            base64_data = base64.b64encode(image_bytes).decode('utf-8')
            
            return f"data:image/png;base64,{base64_data}"
            
        except Exception as e:
            print(f"Error downloading and converting URL image: {e}")
            return None
    
    def convert_bytes_to_base64(self, image_bytes: bytes) -> str:
        """
        Convert image bytes to Base64 data URL
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Base64 data URL string
        """
        try:
            base64_data = base64.b64encode(image_bytes).decode('utf-8')
            return f"data:image/png;base64,{base64_data}"
        except Exception as e:
            print(f"Error converting bytes to base64: {e}")
            return None

# Global instance
image_service = ImageService()
