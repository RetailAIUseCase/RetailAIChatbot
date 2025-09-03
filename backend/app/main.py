"""
Main FastAPI application
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.auth.routes import router as auth_router
from app.database.connection import db
from app.config.settings import settings
from app.projects.routes import router as projects_router
from app.chat.sql_routes import router as sql_chat_router
from app.documents.routes import router as uploaded_document_router
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
        # await db.create_all_tables()  # To create all the tables
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
    allow_origins=[
        settings.FRONTEND_URL,  # Add your Vercel deployment URL here for production  # "https://your-frontend.vercel.app"
        "http://localhost:3000",  # Local development
        "http://127.0.0.1:3000",  # Alternative localhost format
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(sql_chat_router)
app.include_router(uploaded_document_router)

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

# For Railway deployment
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Important for Railway deployment
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development"
    )
