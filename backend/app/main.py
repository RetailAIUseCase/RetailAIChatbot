"""
Main FastAPI application
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routes.auth_routes import router as auth_router
from app.database.connection import db
from app.config.settings import settings
from app.routes.project_routes import router as projects_router
from app.routes.sql_routes import router as sql_chat_router
from app.routes.document_routes import router as uploaded_document_router
from app.routes.websocket_routes import router as websocket_router
from app.routes.purchase_order_routes import router as po_router
# Add to your main.py
from app.routes.visualization_routes import router as visualization_router

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    try:
        settings.validate_settings()
        await db.connect()
        logger.info("Application startup completed")
        yield
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise
    finally:
        # Shutdown
        await db.disconnect()
        logger.info("Application shutdown completed")

# Create FastAPI app
app = FastAPI(
    title="AI Document Intelligence Auth Service",
    description="Authentication service for AI Document Intelligence platform",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in settings.ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(sql_chat_router)
app.include_router(uploaded_document_router)
app.include_router(websocket_router)
app.include_router(po_router)
app.include_router(visualization_router)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI Document Intelligence Auth Service",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Basic database connectivity check
        if db.connection is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        return {
            "status": "healthy",
            "database": "connected",
            "environment": settings.ENVIRONMENT
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

# For deployment
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Important for deployment
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development"
    )
