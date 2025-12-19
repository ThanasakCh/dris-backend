from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from core.database import get_db
from models import User, Field, VISnapshot, VITimeSeries
from schemas import (
    VIAnalysisRequest, VIOverlayRequest, VIOverlayResponse,
    VISnapshotCreate, VISnapshotResponse,
    VITimeSeriesCreate, VITimeSeriesResponse
)
from core.auth import get_current_user
from services import gee_service
from uuid import UUID

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/vi-analysis", tags=["vegetation-indices"])
vi_router = APIRouter(prefix="/vi", tags=["vegetation-indices-compat"])

@vi_router.get("/timeseries/{field_id}")
async def get_vi_timeseries_compat(
    field_id: UUID,
    vi_type: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    analysis_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get VI timeseries data for a field - fetches from GEE when user explicitly requests"""
    # Verify field ownership
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    # Set default date range if not provided
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=90)  # Last 3 months
    
    try:
        # Check if we have COMPLETE cached data for the requested range
        # For full_year analysis, we need data for most months, not just a few
        db_timeseries = db.query(VITimeSeries).filter(
            VITimeSeries.field_id == field_id,
            VITimeSeries.vi_type == vi_type,
            VITimeSeries.measurement_date.between(start_date, end_date)
        ).order_by(VITimeSeries.measurement_date.asc()).all()
        
        # Calculate expected number of data points based on analysis type
        cache_is_complete = False
        if db_timeseries:
            if analysis_type == "full_year":
                # For full year, expect at least 6 months of data
                unique_months = set(ts.measurement_date.month for ts in db_timeseries)
                cache_is_complete = len(unique_months) >= 6
            elif analysis_type == "monthly_range":
                # For monthly range, check if we have data points for the range
                expected_months = (end_date.month - start_date.month + 1) if end_date.month >= start_date.month else 1
                unique_months = set(ts.measurement_date.month for ts in db_timeseries)
                cache_is_complete = len(unique_months) >= expected_months
            elif analysis_type == "ten_year_avg":
                # For 10-year avg, expect at least 5 years of data
                unique_years = set(ts.measurement_date.year for ts in db_timeseries)
                cache_is_complete = len(unique_years) >= 5
            else:
                # Default: accept cached data if we have any
                cache_is_complete = len(db_timeseries) > 0
        
        if cache_is_complete:
            print(f"📦 Using cached data: {len(db_timeseries)} points")
            return {
                "timeseries": [VITimeSeriesResponse.model_validate(ts) for ts in db_timeseries],
                "source": "database"
            }
        
        gee_timeseries = gee_service.get_timeseries_data(
            field.geometry, 
            vi_type, 
            start_date, 
            end_date,
            analysis_type
        )
        
        for datapoint in gee_timeseries:
            measurement_date = datetime.fromisoformat(datapoint['date'].replace('Z', '+00:00'))
            
            existing = db.query(VITimeSeries).filter(
                VITimeSeries.field_id == field_id,
                VITimeSeries.vi_type == vi_type,
                VITimeSeries.measurement_date == measurement_date
            ).first()
            
            if not existing:
                timeseries_entry = VITimeSeries(
                    field_id=field_id,
                    vi_type=vi_type,
                    measurement_date=measurement_date,
                    vi_value=datapoint['value']
                )
                db.add(timeseries_entry)
        
        db.commit()
        
        formatted_timeseries = []
        for d in gee_timeseries:
            formatted_timeseries.append({
                "measurement_date": d['date'],
                "vi_value": d['value']
            })
        
        print(f"✅ Successfully fetched {len(formatted_timeseries)} data points from GEE")
        
        return {
            "timeseries": formatted_timeseries,
            "source": "google_earth_engine",
            "analysis_type": analysis_type,
            "count": len(formatted_timeseries)
        }
        
    except Exception as e:
        print(f"Error getting timeseries data: {e}")
        return {
            "timeseries": [],
            "source": "error",
            "message": f"Failed to get data: {str(e)}"
        }

@vi_router.get("/snapshots/{field_id}")
async def get_vi_snapshots_compat(
    field_id: UUID,
    vi_type: Optional[str] = "NDVI",
    limit: Optional[int] = 4,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get VI snapshots for a field"""
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    snapshots = db.query(VISnapshot).filter(
        VISnapshot.field_id == field_id,
        VISnapshot.vi_type == vi_type
    ).order_by(VISnapshot.snapshot_date.desc()).limit(limit).all()
    
    return [VISnapshotResponse.model_validate(snapshot) for snapshot in snapshots]



@router.post("/overlay", response_model=VIOverlayResponse)
@limiter.limit("10/minute")
def generate_vi_overlay(
    request: Request,
    overlay_request: VIOverlayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate VI overlay for given geometry and parameters"""
    try:
        # Use current date if not specified
        analysis_date = overlay_request.date or datetime.now()
        
        # Get VI statistics from GEE
        stats = gee_service.get_vi_statistics(
            geometry=overlay_request.geometry,
            vi_type=overlay_request.vi_type,
            date=analysis_date
        )
        
        # Generate overlay image
        overlay_url = gee_service.generate_vi_overlay(
            geometry=overlay_request.geometry,
            vi_type=overlay_request.vi_type,
            date=analysis_date
        )
        
        return VIOverlayResponse(
            overlay_url=overlay_url,
            mean_value=stats['mean_value'],
            min_value=stats['min_value'],
            max_value=stats['max_value'],
            analysis_message=stats['analysis_message']
        )
        
    except Exception as e:
        print(f"Error generating VI overlay: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate VI overlay"
        )

@router.delete("/snapshots/{field_id}")
def delete_field_snapshots(
    field_id: UUID,
    vi_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete VI snapshots for a field"""
    # Verify field ownership
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    try:
        # Build query to delete snapshots
        query = db.query(VISnapshot).filter(VISnapshot.field_id == field_id)
        
        if vi_type:
            query = query.filter(VISnapshot.vi_type == vi_type)
            print(f"🗑️ Deleting {vi_type} snapshots for field {field_id}")
        else:
            print(f"🗑️ Deleting ALL snapshots for field {field_id}")
        
        # Get snapshots to delete (for counting)
        snapshots_to_delete = query.all()
        count_to_delete = len(snapshots_to_delete)
        
        # Delete snapshots
        deleted_count = query.delete()
        db.commit()
        
        print(f"✅ Deleted {deleted_count} snapshots")
        
        return {
            "message": f"Deleted {deleted_count} snapshots successfully",
            "deleted_count": deleted_count,
            "vi_type": vi_type or "ALL",
            "field_id": str(field_id)
        }
        
    except Exception as e:
        print(f"❌ Error deleting snapshots: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete snapshots"
        )

@router.post("/{field_id}/analyze-historical")
@limiter.limit("5/minute")
def analyze_historical_vi(
    request: Request,
    field_id: UUID,
    vi_type: str = "NDVI",
    count: int = 4,
    clear_old: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate multiple historical VI snapshots for a field"""
    # Verify field ownership
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    try:
        print(f"🔍 Generating {count} historical {vi_type} snapshots for field {field_id}")
        
        # Clear old snapshots of the same VI type if requested
        if clear_old:
            print(f"🗑️ Clearing old {vi_type} snapshots...")
            old_snapshots = db.query(VISnapshot).filter(
                VISnapshot.field_id == field_id,
                VISnapshot.vi_type == vi_type
            )
            old_count = old_snapshots.count()
            if old_count > 0:
                old_snapshots.delete()
                db.commit()
                print(f"✅ Cleared {old_count} old snapshots")
        
        # Use the new get_latest_images_data function for diverse, clean historical data
        historical_images = gee_service.get_latest_images_data(
            geometry=field.geometry,
            vi_type=vi_type,
            limit=count
        )
        
        if not historical_images:
            print("⚠️ No historical images available, cannot create snapshots")
            return {
                "message": "No historical images available for this field",
                "snapshots_created": 0,
                "vi_type": vi_type,
                "field_id": str(field_id)
            }
        
        snapshots_created = []
        
        for i, image_data in enumerate(historical_images):
            try:
                # Parse the acquisition date
                analysis_date = datetime.fromisoformat(image_data['acquisition_date'].replace('Z', '+00:00'))
                
                print(f"📅 Processing snapshot {i+1}/{len(historical_images)} for date: {analysis_date.strftime('%Y-%m-%d')}")
                
                # Check if snapshot already exists for this date (within same day)
                from sqlalchemy import func, Date
                existing = db.query(VISnapshot).filter(
                    VISnapshot.field_id == field_id,
                    VISnapshot.vi_type == vi_type,
                    func.date(VISnapshot.snapshot_date) == analysis_date.date()
                ).first()
                
                if existing:
                    print(f"⚠️ Snapshot already exists for {analysis_date.date()}, skipping")
                    continue
                
                # Save snapshot to database using data from get_latest_images_data
                snapshot = VISnapshot(
                    field_id=field_id,
                    user_id=current_user.id,
                    vi_type=vi_type,
                    snapshot_date=analysis_date,
                    mean_value=image_data['mean_value'],
                    min_value=image_data['min_value'],
                    max_value=image_data['max_value'],
                    overlay_data=image_data['overlay_url'],
                    status_message=image_data['analysis_message']
                )
                
                db.add(snapshot)
                snapshots_created.append(snapshot)
                
            except Exception as e:
                print(f"❌ Failed to create snapshot {i+1}: {e}")
                continue
        
        # Commit all snapshots at once
        db.commit()
        
        # Refresh all snapshots
        for snapshot in snapshots_created:
            db.refresh(snapshot)
        
        print(f"✅ Successfully created {len(snapshots_created)} historical snapshots from {len(historical_images)} images")
        
        return {
            "message": f"Historical analysis completed for {len(snapshots_created)} snapshots with unique dates",
            "snapshots_created": len(snapshots_created),
            "vi_type": vi_type,
            "field_id": str(field_id),
            "unique_dates": len(set(s.snapshot_date.date() for s in snapshots_created))
        }
        
    except Exception as e:
        print(f"❌ Historical analysis failed: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate historical analysis: {str(e)}"
        )

@router.post("/{field_id}/analyze")
@limiter.limit("10/minute")
def analyze_and_save_vi(
    request: Request,
    field_id: UUID,
    vi_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze VI for a field and save snapshot"""
    # Verify field ownership
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    try:
        analysis_date = datetime.now()
        
        # Get VI statistics from GEE
        stats = gee_service.get_vi_statistics(
            geometry=field.geometry,
            vi_type=vi_type,
            date=analysis_date
        )
        
        # Generate overlay
        overlay_url = gee_service.generate_vi_overlay(
            geometry=field.geometry,
            vi_type=vi_type,
            date=analysis_date
        )
        
        # Save snapshot to database
        snapshot = VISnapshot(
            field_id=field_id,
            user_id=current_user.id,
            vi_type=vi_type,
            snapshot_date=analysis_date,
            mean_value=stats['mean_value'],
            min_value=stats['min_value'],
            max_value=stats['max_value'],
            overlay_data=overlay_url,
            status_message=stats['analysis_message']
        )
        
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        
        return {
            "message": "VI analysis completed and saved",
            "snapshot_id": str(snapshot.id),
            "mean_value": stats['mean_value'],
            "analysis_message": stats['analysis_message']
        }
        
    except Exception as e:
        print(f"Error analyzing and saving VI: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze and save VI"
        )

@router.get("/{field_id}/current")
def get_current_vi_analysis(
    field_id: UUID,
    vi_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current VI analysis for a field - returns latest snapshot from database"""
    # Verify field ownership
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    # Get latest snapshot from database - do NOT auto-fetch from GEE
    latest_snapshot = db.query(VISnapshot).filter(
        VISnapshot.field_id == field_id,
        VISnapshot.vi_type == vi_type
    ).order_by(VISnapshot.snapshot_date.desc()).first()
    
    if latest_snapshot:
        return {
            "field_id": str(field_id),
            "vi_type": vi_type,
            "analysis_date": latest_snapshot.snapshot_date.isoformat(),
            "mean_value": latest_snapshot.mean_value,
            "min_value": latest_snapshot.min_value,
            "max_value": latest_snapshot.max_value,
            "analysis_message": latest_snapshot.status_message,
            "overlay_data": latest_snapshot.overlay_data
        }
    
    # Return empty if no data - user must explicitly analyze to get data
    return {
        "field_id": str(field_id),
        "vi_type": vi_type,
        "analysis_date": None,
        "mean_value": None,
        "min_value": None,
        "max_value": None,
        "analysis_message": "No analysis data available. Please click 'Analyze' to fetch data from satellite.",
        "overlay_data": None
    }

@router.get("/snapshots/{field_id}")
def get_field_snapshots(
    field_id: UUID,
    vi_type: Optional[str] = None,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get VI snapshots for a field - only returns existing data, does NOT auto-create"""
    # Verify field ownership
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    query = db.query(VISnapshot).filter(VISnapshot.field_id == field_id)
    
    if vi_type:
        query = query.filter(VISnapshot.vi_type == vi_type)
    
    snapshots = query.order_by(VISnapshot.snapshot_date.desc()).limit(limit).all()
    
    # Return only existing snapshots - do NOT auto-create from GEE
    # User must explicitly click "analyze" button to fetch new data
    return [VISnapshotResponse.model_validate(snapshot) for snapshot in snapshots]



@router.get("/timeseries/{field_id}")
def get_field_timeseries(
    field_id: UUID,
    vi_type: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    analysis_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get VI timeseries data for a field - fetches from GEE when user explicitly requests"""
    # Verify field ownership
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    # Set default date range if not provided
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=90)  # Last 3 months
    
    try:
        # Check if we have COMPLETE cached data for the requested range
        # For full_year analysis, we need data for most months, not just a few
        db_timeseries = db.query(VITimeSeries).filter(
            VITimeSeries.field_id == field_id,
            VITimeSeries.vi_type == vi_type,
            VITimeSeries.measurement_date.between(start_date, end_date)
        ).order_by(VITimeSeries.measurement_date.asc()).all()
        
        # Calculate expected number of data points based on analysis type
        cache_is_complete = False
        if db_timeseries:
            if analysis_type == "full_year":
                # For full year, expect at least 6 months of data
                unique_months = set(ts.measurement_date.month for ts in db_timeseries)
                cache_is_complete = len(unique_months) >= 6
                print(f"📊 Full year cache check: found {len(unique_months)} unique months")
            elif analysis_type == "monthly_range":
                # For monthly range, check if we have data points for the requested range
                expected_months = (end_date.month - start_date.month + 1) if end_date.month >= start_date.month else 1
                unique_months = set(ts.measurement_date.month for ts in db_timeseries)
                cache_is_complete = len(unique_months) >= expected_months
                print(f"📊 Monthly range cache check: found {len(unique_months)}/{expected_months} months")
            elif analysis_type == "ten_year_avg":
                # For 10-year avg, expect at least 5 years of data
                unique_years = set(ts.measurement_date.year for ts in db_timeseries)
                cache_is_complete = len(unique_years) >= 5
                print(f"📊 10-year cache check: found {len(unique_years)} unique years")
            else:
                # Default: accept cached data if we have any
                cache_is_complete = len(db_timeseries) > 0
        
        if cache_is_complete:
            print(f"📦 Using complete cached data: {len(db_timeseries)} points")
            return {
                "timeseries": [VITimeSeriesResponse.model_validate(ts) for ts in db_timeseries],
                "source": "database",
                "count": len(db_timeseries)
            }
        
        # If no data in database, fetch from Google Earth Engine
        # This is OK because AnalysisPage calls this after user explicitly selects time range
        print(f"🔍 Fetching {vi_type} timeseries from GEE for field {field_id}")
        
        gee_timeseries = gee_service.get_timeseries_data(
            geometry=field.geometry,
            vi_type=vi_type,
            start_date=start_date,
            end_date=end_date,
            analysis_type=analysis_type
        )
        
        # Save to database for future use
        saved_count = 0
        for datapoint in gee_timeseries:
            try:
                if 'T' in datapoint['date']:
                    measurement_date = datetime.fromisoformat(datapoint['date'].replace('Z', '+00:00'))
                else:
                    measurement_date = datetime.fromisoformat(datapoint['date'])
                
                existing = db.query(VITimeSeries).filter(
                    VITimeSeries.field_id == field_id,
                    VITimeSeries.vi_type == vi_type,
                    VITimeSeries.measurement_date == measurement_date
                ).first()
                
                if not existing:
                    timeseries_entry = VITimeSeries(
                        field_id=field_id,
                        vi_type=vi_type,
                        measurement_date=measurement_date,
                        vi_value=datapoint['value']
                    )
                    db.add(timeseries_entry)
                    saved_count += 1
            except Exception as e:
                print(f"Error saving data point: {e}")
                continue
        
        db.commit()
        print(f"💾 Saved {saved_count} new records to database")
        
        # Return the data
        formatted_timeseries = []
        for d in gee_timeseries:
            formatted_timeseries.append({
                "measurement_date": d['date'],
                "vi_value": d['value']
            })
        
        print(f"✅ Successfully fetched {len(formatted_timeseries)} data points from GEE")
        
        return {
            "timeseries": formatted_timeseries,
            "source": "google_earth_engine",
            "analysis_type": analysis_type,
            "count": len(formatted_timeseries)
        }
        
    except Exception as e:
        print(f"❌ Error getting timeseries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get timeseries data: {str(e)}"
        )

# ลบ available-dates endpoint เพราะไม่จำเป็น - frontend จะใช้ข้อมูลแบบ hardcode

@router.get("/latest/{field_id}")  
def get_latest_vi_values(
    field_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get latest VI values for all indices for a field"""
    # Verify field ownership
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    vi_types = ['NDVI', 'EVI', 'GNDVI', 'NDWI', 'SAVI', 'VCI']
    latest_values = {}
    
    for vi_type in vi_types:
        latest_snapshot = db.query(VISnapshot).filter(
            VISnapshot.field_id == field_id,
            VISnapshot.vi_type == vi_type
        ).order_by(VISnapshot.snapshot_date.desc()).first()
        
        if latest_snapshot:
            latest_values[vi_type] = {
                "value": latest_snapshot.mean_value,
                "date": latest_snapshot.snapshot_date.isoformat(),
                "analysis_message": latest_snapshot.analysis_message
            }
        else:
            latest_values[vi_type] = None
    
    return latest_values

@router.post("/bulk-analyze/{field_id}")
@limiter.limit("3/minute")
def bulk_analyze_field(
    request: Request,
    field_id: UUID,
    vi_types: List[str],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze multiple VI types for a field at once"""
    # Verify field ownership
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.user_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found"
        )
    
    results = {}
    analysis_date = datetime.now()
    
    for vi_type in vi_types:
        try:
            # Get VI statistics
            stats = gee_service.get_vi_statistics(
                geometry=field.geometry,
                vi_type=vi_type,
                date=analysis_date
            )
            
            # Generate overlay
            overlay_url = gee_service.generate_vi_overlay(
                geometry=field.geometry,
                vi_type=vi_type,
                date=analysis_date
            )
            
            # Save snapshot
            snapshot = VISnapshot(
                field_id=field_id,
                vi_type=vi_type,
                snapshot_date=analysis_date,
                mean_value=stats['mean_value'],
                min_value=stats['min_value'],
                max_value=stats['max_value'],
                overlay_url=overlay_url,
                analysis_message=stats['analysis_message']
            )
            
            db.add(snapshot)
            
            # Save timeseries entry
            timeseries_entry = VITimeSeries(
                field_id=field_id,
                vi_type=vi_type,
                measurement_date=analysis_date,
                vi_value=stats['mean_value']
            )
            
            db.add(timeseries_entry)
            
            results[vi_type] = {
                "success": True,
                "stats": stats,
                "overlay_url": overlay_url
            }
            
        except Exception as e:
            print(f"Error analyzing {vi_type}: {e}")
            results[vi_type] = {
                "success": False,
                "error": str(e)
            }
    
    db.commit()
    
    return {
        "message": "Bulk analysis completed",
        "results": results,
        "analysis_date": analysis_date.isoformat()
    }
