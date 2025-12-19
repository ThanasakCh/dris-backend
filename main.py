from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import os

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import routers
from routers import auth, fields, vi_analysis, utils, tunnel

# Import database
from core.database import Base, engine

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup: Initialize database and services
    print("Starting Grovi API...")
    
    # Create database tables if they don't exist
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
    except Exception as e:
        print(f"Error creating database tables: {e}")
    
    # Initialize Google Earth Engine (optional - will work without it)
    try:
        from services import gee_service
        print("Google Earth Engine service initialized")
    except Exception as e:
        print(f"Info: Google Earth Engine not available - real satellite data will not be accessible: {e}")
    
    yield
    
    # Shutdown
    print("Shutting down Grovi API...")

# Create FastAPI application
app = FastAPI(
    title="Grovi - Crop Monitoring API",
    description="API for crop monitoring using satellite data and vegetation indices",
    version="1.0.0",
    lifespan=lifespan
)

# Add rate limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://localhost:5173", 
        "http://127.0.0.1:3000", 
        "http://127.0.0.1:5173",
        # Current tunnel URLs (2025-12-13)
        "https://balance-white-wallpaper-nursing.trycloudflare.com",  # Backend
        "https://recent-keywords-groups-millennium.trycloudflare.com",  # Frontend
        # Previous tunnels
        "https://flour-memo-regards-legend.trycloudflare.com",
        "https://sf-polyphonic-scanners-maintenance.trycloudflare.com",
        "https://postage-msie-skilled-insulin.trycloudflare.com",
        "https://visitors-hc-assign-glasses.trycloudflare.com",
    ],
    # Allow any Cloudflare tunnel subdomain
    allow_origin_regex=r"^https://[a-zA-Z0-9-]+\.trycloudflare\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(fields.router)
app.include_router(vi_analysis.router)
app.include_router(vi_analysis.vi_router)
app.include_router(utils.router)
app.include_router(tunnel.router)

@app.get("/")
def read_root():
    """Root endpoint"""
    return {
        "message": "Welcome to Grovi - Crop Monitoring API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "Grovi API is running successfully"
    }

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    print(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "message": "เกิดข้อผิดพลาดภายในระบบ"
        }
    )

if __name__ == "__main__":
    print("Starting Grovi API server...")
    
    # Check production mode via environment variable
    is_production = os.environ.get("PRODUCTION", "false").lower() == "true"
    workers = int(os.environ.get("WORKERS", "4")) if is_production else 1
    
    try:
        if is_production:
            # Production mode: multiple workers, no reload
            print(f"Running in PRODUCTION mode with {workers} workers")
            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=8000,
                workers=workers,
                log_level="info"
            )
        else:
            # Development mode: single worker with reload
            print("Running in DEVELOPMENT mode")
            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=8000,
                reload=True,
                log_level="info"
            )
    except Exception as e:
        print(f"Failed to start server: {e}")
        import traceback
        traceback.print_exc()
