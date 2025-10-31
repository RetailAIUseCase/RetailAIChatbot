"""
Chart generation routes
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.utils.auth_utils import get_current_user
from app.services.visualization_service import chart_service
import logging
import tempfile
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/charts", tags=["charts"])

class ChartRequest(BaseModel):
    data: List[Dict[str, Any]]
    chart_type: str
    title: str
    config: Optional[Dict] = None

class ChartRegenerateRequest(BaseModel):
    conversation_id: str
    chart_type: str

@router.post("/generate")
async def generate_chart(
    request: ChartRequest,
    current_user = Depends(get_current_user)
):
    """Generate a new chart from data"""
    try:
        result = await chart_service.generate_chart(
            data=request.data,
            chart_type=request.chart_type,
            title=request.title,
            config=request.config
        )
        return result
    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/download/html")
async def download_chart_html(
    request: Dict[str, Any],
    current_user = Depends(get_current_user)
):
    """Download chart as standalone HTML"""
    try:
        chart_html = request.get('chart_html')
        if not chart_html:
            raise HTTPException(status_code=400, detail="No chart HTML provided")
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(chart_html)
            temp_path = f.name
        
        return FileResponse(
            temp_path,
            media_type='text/html',
            filename=f"chart_{request.get('title', 'visualization')}.html"
        )
    except Exception as e:
        logger.error(f"Chart download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/types")
async def get_chart_types():
    """Get available chart types"""
    return {"chart_types": chart_service.CHART_TYPES}
