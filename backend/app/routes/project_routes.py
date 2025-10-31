# app/projects/routes.py
"""
Project management routes
"""
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List
from pydantic import BaseModel
from app.utils.auth_utils import get_current_user
from app.database.connection import db
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])
security = HTTPBearer()

class ProjectCreate(BaseModel):
    name: str
    description: str = ""

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    updated_at: str

@router.post("/", response_model=ProjectResponse)
async def create_project(
    project_data: ProjectCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new project"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        project = await db.create_project(
            user_id=user["id"],
            name=project_data.name,
            description=project_data.description
        )
        
        return ProjectResponse(**project)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create project error: {e}")
        if "unique constraint" in str(e).lower():
            raise HTTPException(status_code=400, detail="Project name already exists")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/", response_model=List[ProjectResponse])
async def get_user_projects(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get all projects for the authenticated user"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        projects = await db.get_user_projects(user["id"])
        return [ProjectResponse(**project) for project in projects]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get projects error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Delete a project"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        success = await db.delete_project(project_id, user["id"])
        if not success:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return {"message": "Project deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete project error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
