"""
Purchase Order workflow routes
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, Path, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
from typing import List, Optional
from pydantic import BaseModel, Field
from app.utils.auth_utils import get_current_user
from app.utils.date_parser import parse_user_date_safe
from app.services.po_workflow_service import po_workflow_service
from app.services.storage_service import storage_service
from app.services.email_service import email_service
from app.websocket.connection_manager import manager
from app.database.connection import db
import logging

from app.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/po", tags=["purchase-orders"])
security = HTTPBearer()

# Request Models
class GeneratePORequest(BaseModel):
    order_date: str = Field(..., description="Order date in YYYY-MM-DD format")
    trigger_query: Optional[str] = Field(None, description="User query that triggered PO generation")

class ApprovalRequest(BaseModel):  # Changed from plain class to Pydantic model
    comment: Optional[str] = Field(None, description="Optional approval comment")

class RejectionRequest(BaseModel):  # Changed from plain class to Pydantic model
    reason: str = Field(None, description="Required rejection reason")

# Response Models
class POSummary(BaseModel):
    po_number: str
    vendor_name: str
    total_amount: float
    status: str
    needs_approval: bool
    order_date: str
    created_at: str

class WorkflowStatus(BaseModel):
    workflow_id: str
    status: str
    current_step: int
    step_results: Optional[dict] = None
    error_message: Optional[str] = None


@router.post("/generate", response_model=dict)
async def generate_po_workflow(
    request: GeneratePORequest,
    project_id: str = Query(..., description="Project ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Start PO generation workflow (non-blocking)
    
    This endpoint triggers the complete PO workflow:
    1. Checks SKU shortfalls
    2. Analyzes packaging material requirements  
    3. Gets vendor pricing
    4. Generates PO documents
    5. Sends for approval or directly to vendor
    """
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Validate project access
        project = await db.get_project_by_id(project_id, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        original_date_input = request.order_date
        parsed_date, is_valid = parse_user_date_safe(request.order_date)
        
        logger.info(f"📅 Date parsing: '{original_date_input}' -> '{parsed_date}' (valid: {is_valid})")
        
        # From here on, we always use the standardized date format
        standardized_order_date = parsed_date

        # Start workflow in background
        result = await po_workflow_service.start_po_workflow(
            user_id=user["id"],
            project_id=project_id,
            order_date=standardized_order_date,
            trigger_query=request.trigger_query
        )
        
        return {
            **result,
            "project_name": project["name"],
            "order_date": standardized_order_date
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PO generation API error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    

@router.get("/project/{project_id}", response_model=dict)
async def get_project_pos(
    project_id: str = Path(..., description="Project ID"),
    order_date: Optional[str] = Query(None, description="Filter by order date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Number of POs to return"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get POs for a project with optional filters
    
    Returns list of purchase orders with pagination and filtering options.
    """
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Validate project access
        project = await db.get_project_by_id(project_id, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get POs with filters
        if order_date:
            pos = await db.fetch_pos_by_date(user["id"], project_id, order_date)
        else:
            pos = await db.fetch_all_pos_by_project(user["id"], project_id)
        
        # Apply status filter if provided
        if status:
            pos = [po for po in pos if po["status"] == status]
        
        # Apply limit
        pos = pos[:limit]
        
        # Calculate summary statistics
        total_amount = sum(float(po["total_amount"]) for po in pos)
        status_counts = {}
        for po in pos:
            po_status = po["status"]
            status_counts[po_status] = status_counts.get(po_status, 0) + 1
        
        return {
            "pos": pos,
            "count": len(pos),
            "project_name": project["name"],
            "summary": {
                "total_amount": total_amount,
                "status_breakdown": status_counts
            },
            "filters_applied": {
                "order_date": order_date,
                "status": status,
                "limit": limit
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get project POs API error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.get("/details/{po_number}", response_model=dict)
async def get_po_details(
    po_number: str = Path(..., description="PO Number"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get detailed information for a specific PO
    
    Returns complete PO details including line items and status history.
    """
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        po_details = await db.get_po_details_with_items(po_number, user["id"])
        if not po_details:
            raise HTTPException(status_code=404, detail="PO not found")
        
        return {
            "po_details": po_details,
            "can_approve": False,  # Add role-based logic here if needed
            "can_modify": po_details["status"] in ["pending", "rejected"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get PO details API error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/workflow/{workflow_id}/status", response_model=dict)
async def get_workflow_status(
    workflow_id: str = Path(..., description="Workflow ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get real-time workflow progress status
    
    Returns current step, progress, and any generated POs.
    """
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        workflow_status = await po_workflow_service.get_workflow_progress(workflow_id, user["id"])
        if not workflow_status:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        return {
            "workflow_status": workflow_status,
            "progress_percentage": min(100, (workflow_status.get("current_step", 0) / 5) * 100),
            "is_complete": workflow_status.get("status") == "completed",
            "has_errors": workflow_status.get("status") == "failed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workflow status API error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/download/{po_number}", response_model=dict)
async def get_po_download_url(
    po_number: str = Path(..., description="PO Number"),
    expiry_minutes: int = Query(60, ge=5, le=1440, description="URL expiry in minutes"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Generate secure download URL for PO PDF
    
    Returns time-limited signed URL for downloading PO document.
    """
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Get PO details to verify access
        po_details = await db.get_po_details_with_items(po_number, user["id"])
        if not po_details:
            raise HTTPException(status_code=404, detail="PO not found")
        
        try:
            pdf_bytes = await storage_service.download_po_pdf(po_details['pdf_path'])
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{po_number}.pdf"',
                    "Content-Type": "application/pdf"
                }
            )
        except HTTPException:
            raise
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PO download URL API error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.get("/view/{po_number}")
async def view_po_pdf_inline(
    po_number: str = Path(..., description="PO Number"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    View PO PDF inline in browser tab (opens for viewing, doesn't download)
    """
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        po_details = await db.get_po_details_with_items(po_number, user["id"])
        if not po_details:
            raise HTTPException(status_code=404, detail="PO not found")
        
        pdf_path = po_details.get('pdf_path')
        if not pdf_path:
            raise HTTPException(status_code=404, detail="PDF not available")
        
        # Download PDF bytes from storage
        pdf_bytes = await storage_service.download_po_pdf(pdf_path)
        
        # Return PDF for inline viewing (opens in browser tab)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{po_number}.pdf"',  # ← "inline" = opens in browser
                "Content-Type": "application/pdf"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF view error for {po_number}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dashboard/{project_id}", response_model=dict)
async def get_po_dashboard(
    project_id: str = Path(..., description="Project ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get PO dashboard data with analytics
    
    Returns summary statistics and recent activity for PO management dashboard.
    """
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Validate project access
        project = await db.get_project_by_id(project_id, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get all POs for analytics
        all_pos = await db.fetch_all_pos_by_project(user["id"], project_id)
        
        # Calculate analytics
        total_pos = len(all_pos)
        total_amount = sum(float(po["total_amount"]) for po in all_pos)
        
        status_counts = {}
        monthly_totals = {}
        
        for po in all_pos:
            # Status breakdown
            status = po["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # Monthly totals
            month = po["order_date"][:7]  # YYYY-MM
            if month not in monthly_totals:
                monthly_totals[month] = {"count": 0, "amount": 0}
            monthly_totals[month]["count"] += 1
            monthly_totals[month]["amount"] += float(po["total_amount"])
        
        # Recent activity (last 10 POs)
        recent_pos = sorted(all_pos, key=lambda x: x["created_at"], reverse=True)[:10]
        
        return {
            "project_name": project["name"],
            "summary": {
                "total_pos": total_pos,
                "total_amount": total_amount,
                "average_po_amount": total_amount / total_pos if total_pos > 0 else 0,
                "status_breakdown": status_counts
            },
            "analytics": {
                "monthly_trends": monthly_totals,
                "pending_approvals": status_counts.get("pending_approval", 0)
            },
            "recent_activity": recent_pos
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PO dashboard API error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/cancel/{po_number}", response_model=dict)
async def cancel_purchase_order(
    po_number: str = Path(..., description="PO Number to cancel"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Cancel a purchase order
    
    Only allowed for POs in pending or rejected status.
    """
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Get PO details to verify status and ownership
        po_details = await db.get_po_details_with_items(po_number, user["id"])
        if not po_details:
            raise HTTPException(status_code=404, detail="PO not found")
        
        # Check if cancellation is allowed
        if po_details["status"] not in ["pending", "rejected"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot cancel PO with status '{po_details['status']}'"
            )
        
        # Update status to cancelled
        await db.update_po_status(po_number, "cancelled", "Cancelled by user")
        
        return {
            "success": True,
            "message": f"PO {po_number} cancelled successfully",
            "cancelled_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PO cancellation API error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# TOKEN-BASED APPROVAL ROUTES (Used by email links - NO AUTH REQUIRED)

@router.get("/approval/{token}", response_model=dict)
async def get_approval_details(token: str = Path(...)):
    """Get PO details for approval using token (called by frontend if needed)"""
    try:
        approval_details = await db.validate_approval_token(token)
        
        if not approval_details:
            raise HTTPException(status_code=404, detail="Invalid or expired approval token")
        
        if approval_details["status"] != "pending":
            return {
                "already_processed": True,
                "status": approval_details["status"],
                "po_number": approval_details["po_number"],
                "message": f"This PO has already been {approval_details['status']}"
            }
        
        # Get PO details
        async with db.pool.acquire() as connection:
            po_details = await connection.fetchrow("""
                SELECT po_number, vendor_name, vendor_email, total_amount, 
                       status, order_date, created_at::text, pdf_path
                FROM purchase_orders WHERE po_number = $1
            """, approval_details["po_number"])
            
            if not po_details:
                raise HTTPException(status_code=404, detail="PO not found")
            
            po_items = await connection.fetch("""
                SELECT matnr, matdesc, matcat, quantity, unit_cost, total_cost
                FROM po_line_items WHERE po_number = $1 ORDER BY matcat, matnr
            """, approval_details["po_number"])
        
        return {
            "approval_valid": True,
            "assigned_approver": approval_details["approver_email"],
            "token_expires_at": approval_details["token_expires_at"].isoformat(),
            "po_details": dict(po_details),
            "po_items": [dict(item) for item in po_items],
            "can_approve": True,
            "approval_threshold": settings.PO_APPROVAL_THRESHOLD
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get approval details error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/approval/{token}/download", response_model=dict)
async def download_po_from_approval(token: str = Path(...)):
    """Download PO PDF using approval token"""
    try:
        approval_details = await db.validate_approval_token(token)
        
        if not approval_details:
            raise HTTPException(status_code=404, detail="Invalid or expired approval token")
        
        async with db.pool.acquire() as connection:
            po_details = await connection.fetchrow("""
                SELECT po_number, pdf_path, vendor_name, total_amount
                FROM purchase_orders WHERE po_number = $1
            """, approval_details["po_number"])
            
            if not po_details:
                raise HTTPException(status_code=404, detail="PO not found")
        
        try:
            pdf_bytes = await storage_service.download_po_pdf(po_details['pdf_path'])
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{approval_details["po_number"]}.pdf"',
                    "Content-Type": "application/pdf"
                }
            )
        except HTTPException:
            raise
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approval PDF download error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# DIRECT APPROVAL/REJECTION ROUTES (Email link destinations - HTML responses)

@router.get("/approval/{token}/approve-direct", response_class=HTMLResponse)
async def show_approval_form(
    token: str = Path(...),
    approver_email: str = Query(...)
):
    """Show approval form (GET) - Called when finance manager clicks email link"""
    try:
        approval_details = await db.validate_approval_token(token)
        print(approval_details)
        # Validation checks
        if not approval_details:
            return """<html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">❌ Invalid or Expired Token</h1>
                <p>This approval link is no longer valid.</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #dc3545; color: white; border: none; border-radius: 5px;">Close</button>
            </body></html>"""
        
        if approval_details["status"] != "pending":
            return f"""<html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1>ℹ️ Already Processed</h1>
                <p>This PO has already been {approval_details["status"]}.</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 5px;">Close</button>
            </body></html>"""
        
        if approver_email.lower() != approval_details["approver_email"].lower():
            return """<html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">❌ Unauthorized</h1>
                <p>You are not authorized to approve this PO.</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #dc3545; color: white; border: none; border-radius: 5px;">Close</button>
            </body></html>"""
        
        # Show approval form
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Approve PO {approval_details['po_number']}</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #f5f5f5; }}
                .container {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
                .header {{ background: #28a745; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; margin: -30px -30px 30px -30px; }}
                .btn {{ background: #28a745; color: white; padding: 15px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }}
                textarea {{ width: 100%; padding: 10px; margin: 5px 0; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="color: white; margin: 0;">✅ Approve Purchase Order</h1>
                </div>
                
                <h2>PO Number: {approval_details['po_number']}</h2>
                <p><strong>Vendor:</strong> {approval_details['vendor_name']}</p>
                <p><strong>Amount:</strong> ${approval_details['total_amount']:,.2f}</p>
                <p><strong>Approver:</strong> {approver_email}</p>
                
                <form method="post" action="/po/approval/{token}/approve-direct?approver_email={approver_email}">
                    <div style="margin: 20px 0;">
                        <label>Comment (Optional):</label><br>
                        <textarea name="comment" rows="3" placeholder="Add any approval comments..."></textarea>
                    </div>
                    
                    <div style="text-align: center;">
                        <button type="submit" class="btn">✅ CONFIRM APPROVAL</button>
                    </div>
                </form>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        logger.error(f"Error showing approval form: {e}")
        return "<html><body style='text-align: center; padding: 50px;'><h1>Error</h1><p>System error occurred.</p></body></html>"

@router.post("/approval/{token}/approve-direct", response_class=HTMLResponse)
async def process_approval_form(
    request: Request,
    token: str = Path(...),
    approver_email: str = Query(...)
):
    """Process approval form submission (POST)"""
    try:
        form = await request.form()
        comment = form.get("comment", "").strip()
        
        # Use your existing workflow service method
        result = await po_workflow_service.approve_po_with_token(
            token=token,
            approver_email=approver_email,
            comment=comment if comment else None
        )
        
        if result["success"]:
            return f"""
            <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <div style="background: #d4edda; border: 2px solid #28a745; padding: 30px; border-radius: 10px; max-width: 500px; margin: 0 auto;">
                    <h1 style="color: #155724;">✅ PO Approved Successfully!</h1>
                    <p>Purchase Order <strong>{result.get('po_number', '')}</strong> has been approved and sent to the vendor.</p>
                    <p>All relevant parties have been notified.</p>
                    <button onclick="window.close()" style="background: #28a745; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; margin-top: 20px;">
                        Close Window
                    </button>
                </div>
            </body></html>
            """
        else:
            return f"""
            <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <div style="background: #f8d7da; border: 2px solid #dc3545; padding: 30px; border-radius: 10px; max-width: 500px; margin: 0 auto;">
                    <h1 style="color: #721c24;">❌ Approval Failed</h1>
                    <p>{result.get('error', 'Unknown error occurred')}</p>
                    <button onclick="window.close()" style="background: #dc3545; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; margin-top: 20px;">
                        Close Window
                    </button>
                </div>
            </body></html>
            """
        
    except Exception as e:
        logger.error(f"Error processing approval: {e}")
        return "<html><body style='text-align: center; padding: 50px;'><h1>Error</h1><p>System error occurred.</p></body></html>"

@router.get("/approval/{token}/reject-direct", response_class=HTMLResponse)
async def show_rejection_form(
    token: str = Path(...),
    approver_email: str = Query(...)
):
    """Show rejection form (GET) - Called when finance manager clicks email link"""
    try:
        approval_details = await db.validate_approval_token(token)
        
        # Same validation checks as approval
        if not approval_details:
            return """<html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">❌ Invalid or Expired Token</h1>
                <p>This rejection link is no longer valid.</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #dc3545; color: white; border: none; border-radius: 5px;">Close</button>
            </body></html>"""
        
        if approval_details["status"] != "pending":
            return f"""<html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1>ℹ️ Already Processed</h1>
                <p>This PO has already been {approval_details["status"]}.</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 5px;">Close</button>
            </body></html>"""
        
        if approver_email.lower() != approval_details["approver_email"].lower():
            return """<html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">❌ Unauthorized</h1>
                <p>You are not authorized to reject this PO.</p>
                <button onclick="window.close()" style="padding: 10px 20px; background: #dc3545; color: white; border: none; border-radius: 5px;">Close</button>
            </body></html>"""
        
        # Show rejection form
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Reject PO {approval_details['po_number']}</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #f5f5f5; }}
                .container {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
                .header {{ background: #dc3545; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; margin: -30px -30px 30px -30px; }}
                .btn {{ background: #dc3545; color: white; padding: 15px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }}
                textarea {{ width: 100%; padding: 10px; margin: 5px 0; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="color: white; margin: 0;">❌ Reject Purchase Order</h1>
                </div>
                
                <h2>PO Number: {approval_details['po_number']}</h2>
                <p><strong>Vendor:</strong> {approval_details['vendor_name']}</p>
                <p><strong>Amount:</strong> ${approval_details['total_amount']:,.2f}</p>
                <p><strong>Approver:</strong> {approver_email}</p>
                
                <form method="post" action="/po/approval/{token}/reject-direct?approver_email={approver_email}">
                    <div style="margin: 20px 0;">
                        <label>Rejection Reason (Required):</label><br>
                        <textarea name="reason" rows="4" required placeholder="Please provide detailed reason for rejection..."></textarea>
                    </div>
                    
                    <div style="text-align: center;">
                        <button type="submit" class="btn">❌ CONFIRM REJECTION</button>
                    </div>
                </form>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        logger.error(f"Error showing rejection form: {e}")
        return "<html><body style='text-align: center; padding: 50px;'><h1>Error</h1><p>System error occurred.</p></body></html>"

@router.post("/approval/{token}/reject-direct", response_class=HTMLResponse)
async def process_rejection_form(
    request: Request,
    token: str = Path(...),
    approver_email: str = Query(...)
):
    """Process rejection form submission (POST)"""
    try:
        form = await request.form()
        reason = form.get("reason", "").strip()
        
        if not reason:
            return """<html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">❌ Error</h1>
                <p>Rejection reason is required.</p>
                <button onclick="history.back()" style="padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 5px;">Go Back</button>
            </body></html>"""
        
        # Use your existing workflow service method
        result = await po_workflow_service.reject_po_with_token(
            token=token,
            approver_email=approver_email,
            reason=reason
        )
        
        if result["success"]:
            return f"""
            <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <div style="background: #f8d7da; border: 2px solid #dc3545; padding: 30px; border-radius: 10px; max-width: 500px; margin: 0 auto;">
                    <h1 style="color: #721c24;">❌ PO Rejected Successfully</h1>
                    <p>Purchase Order <strong>{result.get('po_number', '')}</strong> has been rejected.</p>
                    <p>The requester has been notified with your rejection reason.</p>
                    <button onclick="window.close()" style="background: #dc3545; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; margin-top: 20px;">
                        Close Window
                    </button>
                </div>
            </body></html>
            """
        else:
            return f"""
            <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <div style="background: #f8d7da; border: 2px solid #dc3545; padding: 30px; border-radius: 10px; max-width: 500px; margin: 0 auto;">
                    <h1 style="color: #721c24;">❌ Rejection Failed</h1>
                    <p>{result.get('error', 'Unknown error occurred')}</p>
                    <button onclick="window.close()" style="background: #dc3545; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; margin-top: 20px;">
                        Close Window
                    </button>
                </div>
            </body></html>
            """
        
    except Exception as e:
        logger.error(f"Error processing rejection: {e}")
        return "<html><body style='text-align: center; padding: 50px;'><h1>Error</h1><p>System error occurred.</p></body></html>"

# LEGACY AUTHENTICATED ROUTES (Keep for backward compatibility if needed)

@router.post("/approve/{po_number}", response_model=dict)
async def approve_purchase_order_legacy(
    po_number: str = Path(...),
    request: ApprovalRequest = ApprovalRequest(),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Legacy approval endpoint - restricted to assigned approvers"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Check if user is the assigned approver
        async with db.pool.acquire() as connection:
            approval_request = await connection.fetchrow("""
                SELECT approver_email, status FROM po_approval_requests WHERE po_number = $1
            """, po_number)
        
        if not approval_request:
            raise HTTPException(status_code=404, detail="No approval request found")
        
        if (approval_request["approver_email"] and 
            user["email"].lower() != approval_request["approver_email"].lower()):
            return {
                "success": False,
                "error": "Access denied: Only the assigned finance manager can approve this PO",
                "assigned_approver": approval_request["approver_email"],
                "your_email": user["email"]
            }
        
        result = await po_workflow_service.approve_po(
            po_number=po_number,
            approver_email=user["email"],
            comment=request.comment
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Legacy PO approval error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/reject/{po_number}", response_model=dict)
async def reject_purchase_order_legacy(
    po_number: str = Path(...),
    request: RejectionRequest = RejectionRequest(),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Legacy rejection endpoint - restricted to assigned approvers"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Check if user is the assigned approver
        async with db.pool.acquire() as connection:
            approval_request = await connection.fetchrow("""
                SELECT approver_email, status FROM po_approval_requests WHERE po_number = $1
            """, po_number)
        
        if not approval_request:
            raise HTTPException(status_code=404, detail="No approval request found")
        
        if (approval_request["approver_email"] and 
            user["email"].lower() != approval_request["approver_email"].lower()):
            return {
                "success": False,
                "error": "Access denied: Only the assigned finance manager can reject this PO",
                "assigned_approver": approval_request["approver_email"],
                "your_email": user["email"]
            }
        
        result = await po_workflow_service.reject_po(
            po_number=po_number,
            approver_email=user["email"],
            reason=request.reason
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Legacy PO rejection error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")