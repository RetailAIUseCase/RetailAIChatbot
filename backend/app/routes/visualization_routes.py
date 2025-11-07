"""
Chart generation routes
"""
from fastapi import APIRouter, HTTPException, Depends, Response, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from app.utils.auth_utils import get_current_user
from app.services.visualization_service import chart_service
from app.database.connection import db
import logging
import tempfile
import json
from io import BytesIO

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/visualizations", tags=["visualizations"])
security = HTTPBearer()

class ChartRequest(BaseModel):
    data: List[Dict[str, Any]]
    chart_type: str
    title: str
    config: Optional[Dict] = None

class ChartRegenerateRequest(BaseModel):
    conversation_id: str
    chart_type: str

class MultiChartPDFRequest(BaseModel):
    """Request to generate PDF from multiple charts"""
    chart_ids: List[str]
    report_title: Optional[str] = "Analytics Report"
    include_insights: Optional[bool] = True
    conversation_id: Optional[str] = None  # Optional, not used but accepted

# ==================== ERROR HANDLERS ====================

@router.post("/debug/validate")
async def debug_validate(request: Request):
    """Debug endpoint - validate request without processing"""
    try:
        body = await request.body()
        text = body.decode('utf-8')
        logger.info(f"Raw body: {text}")
        
        parsed = json.loads(text)
        logger.info(f"Parsed JSON: {parsed}")
        
        # Try to validate with Pydantic
        try:
            validated = MultiChartPDFRequest(**parsed)
            return {
                "success": True,
                "validated": validated.dict(),
                "message": "Request is valid ✅"
            }
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {
                "success": False,
                "error": str(e),
                "parsed": parsed,
                "message": "Validation failed ❌"
            }
    except Exception as e:
        logger.error(f"Debug error: {e}")
        return {"error": str(e)}
    
@router.get("/types")
async def get_chart_types():
    """Get available chart types"""
    return {"chart_types": chart_service.CHART_TYPES}
    
@router.post("/generate-pdf")
async def generate_multi_chart_pdf(
    request: MultiChartPDFRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Generate PDF"""
    
    try:
        logger.info("=" * 60)
        logger.info("📊 PDF DOWNLOAD REQUEST")
        logger.info("=" * 60)
        
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        chart_ids = request.chart_ids or []
        report_title = request.report_title or "Analytics Report"
        
        logger.info(f"📋 Request: chart_ids={chart_ids}, title={report_title}")
        
        # Validate
        if not chart_ids or len(chart_ids) == 0:
            logger.error("❌ chart_ids is empty")
            raise HTTPException(status_code=400, detail="chart_ids required")
        
        # Fetch charts
        logger.info(f"🔍 Fetching {len(chart_ids)} charts...")

        # Fetch charts from history
        charts_data = await db.get_charts_by_ids(
            request.chart_ids,
            user["id"]
        )
        
        if not charts_data:
            logger.warning(f"No charts found for IDs: {request.chart_ids}")
            raise HTTPException(status_code=404, detail="No charts found")
        
        logger.info(f"✅ Found {len(charts_data)} charts in database")

        # Convert to list of dicts
        charts = []
        for row in charts_data:
            data_summary = row.get('data_summary', {})
            if isinstance(data_summary, str):
                import json
                try:
                    data_summary = json.loads(data_summary)
                except:
                    logger.warning(f"Failed to parse data_summary: {e}")
                    data_summary = {}
            charts.append({
                'success': True,
                'chart_id': row['chart_id'],
                'chart_type': row['chart_type'],
                'title': row['title'],
                'chart_png_base64': row['chart_png_base64'],
                'chart_html': row.get('chart_html'),
                'data_points': data_summary.get('data_points',0)
            })
        
        # Generate PDF
        logger.info("🔄 Generating PDF...")
        pdf_bytes = await chart_service.generate_multi_chart_pdf(
            charts=charts,
            title=request.report_title,
            user_name=user.get("full_name", "User")
        )
        logger.info(f"✅ PDF generated successfully ({len(pdf_bytes)} bytes)")
        # Return as downloadable file
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={request.report_title.replace(' ', '_')}.pdf"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.get("/conversation/{conversation_id}/charts")
async def get_conversation_charts(
    conversation_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all charts from a conversation"""
    
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        charts = await db.get_conversation_charts(
            conversation_id,
            user["id"]
        )
        
        return {
            "success": True,
            "charts": [dict(row) for row in charts],
            "total_charts": len(charts)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching charts: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.delete("/chart/{chart_id}")
async def delete_chart(
    chart_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Delete a chart"""
    
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        deleted = await db.delete_chart(chart_id, user["id"])
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Chart not found")
        
        return {
            "success": True,
            "message": "Chart deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_chart_statistics(
    project_id: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get user's chart generation statistics"""
    
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        stats = await db.get_user_chart_statistics(user["id"], project_id)
        
        return {
            "success": True,
            "statistics": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
