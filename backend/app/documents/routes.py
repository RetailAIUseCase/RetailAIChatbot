"""
Document management routes
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from typing import List
from pydantic import BaseModel
from app.utils.auth_utils import get_current_user
from app.database.connection import db
from app.services.storage_service import storage_service
from app.services.document_processor import document_processor
import logging
import uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
security = HTTPBearer()

class DocumentResponse(BaseModel):
    id: str
    name: str
    original_filename: str
    file_size: int
    mime_type: str
    document_type: str
    upload_status: str
    embedding_status: str
    created_at: str

class BatchUploadResponse(BaseModel):
    success: bool  # Added for consistent response structure
    success_count: int
    failed_count: int
    documents: List[DocumentResponse]
    errors: List[dict]

@router.post("/upload", response_model=BatchUploadResponse)
async def upload_documents(
    background_tasks: BackgroundTasks,
    project_id: str = Form(...),
    document_type: str = Form(...),
    files: List[UploadFile] = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Upload multiple documents"""
    try:
        # Authenticate user
        user = await get_current_user(credentials.credentials)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Invalid authentication"}
            )
        
        # Verify project ownership
        project = await db.get_project_by_id(project_id, user["id"])
        if not project:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Project not found"}
            )
        
        # Validate document type
        valid_types = ['metadata', 'businesslogic', 'references']
        if document_type not in valid_types:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"Invalid document type. Must be one of: {valid_types}"}
            )
        
        # Validate files
        if not files or len(files) == 0:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No files provided"}
            )

        # Check for empty files
        empty_files = [f.filename for f in files if f.size == 0 or not f.filename]
        if empty_files:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"Empty or invalid files: {empty_files}"}
            )

        # Ensure buckets exist
        await storage_service.create_buckets_if_not_exist()

        successful_uploads = []
        failed_uploads = []
        errors = []
        
        for file in files:
            try:
                logger.info(f"Processing file: {file.filename}, size: {file.size}, type: {file.content_type}")
                
                # Upload file to storage
                storage_result = await storage_service.upload_file(file, user["id"], project_id, document_type)
                
                # Create document record
                document_id = str(uuid.uuid4())
                document = await db.create_document(
                    id=document_id,
                    project_id=project_id,
                    user_id=user["id"],
                    name=file.filename,
                    original_filename=file.filename,
                    file_path=storage_result["file_path"],
                    bucket_name=storage_result["bucket_name"],
                    file_size=storage_result["file_size"],
                    mime_type=storage_result["content_type"],
                    document_type=document_type
                )
                
                successful_uploads.append(DocumentResponse(**document))
                
                # Process document in background
                background_tasks.add_task(
                    document_processor.process_document,
                    document_id,
                    storage_result["file_path"],
                    document_type,
                    storage_result["bucket_name"]
                )
                
                logger.info(f"Successfully uploaded: {file.filename}")
                
            except Exception as e:
                logger.error(f"Failed to upload file {file.filename}: {str(e)}")
                errors.append({
                    "filename": file.filename,
                    "error": str(e)
                })
                failed_uploads.append(file.filename)
        
        # Always return JSON with consistent structure
        response_data = BatchUploadResponse(
            success=len(successful_uploads) > 0,
            success_count=len(successful_uploads),
            failed_count=len(failed_uploads),
            documents=successful_uploads,
            errors=errors
        )
        
        # Return appropriate status code
        if len(successful_uploads) == 0:
            return JSONResponse(
                status_code=400,
                content=response_data.dict()
            )
        elif len(failed_uploads) > 0:
            return JSONResponse(
                status_code=207,  # Multi-status for partial success
                content=response_data.dict()
            )
        else:
            return response_data
        
    except HTTPException as he:
        logger.error(f"HTTP error in upload: {he.detail}")
        return JSONResponse(
            status_code=he.status_code,
            content={"success": False, "error": he.detail}
        )
    except Exception as e:
        logger.error(f"Unexpected upload error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"}
        )

@router.get("/project/{project_id}")
async def get_project_documents(
    project_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all documents for a project"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Invalid authentication"}
            )
        
        # Verify project ownership
        project = await db.get_project_by_id(project_id, user["id"])
        if not project:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Project not found"}
            )
        
        documents = await db.get_project_documents(project_id, user["id"])
    #     return {
    #         "success": True,
    #         "documents": [DocumentResponse(**doc) for doc in documents]
    #     }
        
    # except HTTPException as he:
    #     return JSONResponse(
    #         status_code=he.status_code,
    #         content={"success": False, "error": he.detail}
    #     )
    # Get document counts by type
        counts = await db.get_project_document_counts_by_type(project_id, user["id"])
        
        return {
            "success": True,
            "documents": [DocumentResponse(**doc) for doc in documents],
            "counts": {
                "metadata": counts.get("metadata", 0),
                "businesslogic": counts.get("businesslogic", 0), 
                "references": counts.get("references", 0),
                "total": sum(counts.values())
            }
        }
        
    except Exception as e:
        logger.error(f"Get documents error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"}
        )

# **NEW: Health check endpoint**
@router.get("/health")
async def health_check():
    """Health check for document service"""
    return {"status": "healthy", "service": "documents"}

# **NEW: Get document by ID**
@router.get("/{document_id}")
async def get_document(
    document_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get a specific document by ID"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Invalid authentication"}
            )
        
        # You'll need to add this method to your db class
        document = await db.get_document_by_id(document_id, user["id"])
        if not document:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Document not found"}
            )
        
        return {
            "success": True,
            "document": DocumentResponse(**document)
        }
        
    except HTTPException as he:
        return JSONResponse(
            status_code=he.status_code,
            content={"success": False, "error": he.detail}
        )
    except Exception as e:
        logger.error(f"Get document error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"}
        )

# **NEW: Delete document**
@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Delete a document"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Invalid authentication"}
            )
        
        # Get document first to verify ownership
        document = await db.get_document_by_id(document_id, user["id"])
        if not document:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Document not found"}
            )
        
        # Delete from storage
        await storage_service.delete_file(document["file_path"], document["bucket_name"])
        
        # Delete from database (you'll need to implement this)
        await db.delete_document(document_id, user["id"])
        
        return {"success": True, "message": "Document deleted successfully"}
        
    except HTTPException as he:
        return JSONResponse(
            status_code=he.status_code,
            content={"success": False, "error": he.detail}
        )
    except Exception as e:
        logger.error(f"Delete document error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"}
        )
@router.get("/project/{project_id}/embedding-status")
async def get_embedding_status(
    project_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get embedding processing status for a project"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Invalid authentication"}
            )
        
        project = await db.get_project_by_id(project_id, user["id"])
        if not project:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Project not found"}
            )
        
        status = await db.get_project_embedding_status(project_id, user["id"])
        return {
            "success": True,
            "embedding_status": status,
            "is_processing": status['processing'] > 0 or status['pending'] > 0
        }
        
    except Exception as e:
        logger.error(f"Error getting embedding status: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"}
        )
