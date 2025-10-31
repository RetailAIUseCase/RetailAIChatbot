"""
Authentication routes
"""
from datetime import timedelta
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth.models import UserCreate, UserLogin, User, Token
from app.utils.auth_utils import (
    get_password_hash, 
    authenticate_user, 
    create_access_token,
    get_current_user
)
from app.database.connection import db
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """Register a new user"""
    try:
        # Check if user already exists
        existing_user = await db.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Hash password and create user
        hashed_password = get_password_hash(user_data.password)
        user = await db.create_user(
            email=user_data.email,
            hashed_password=hashed_password,
            full_name=user_data.full_name
        )
        
        logger.info(f"New user registered: {user_data.email}")
        return User(**user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    """Login user and return JWT token"""
    try:
        user = await authenticate_user(user_data.email, user_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["email"]}, 
            expires_delta=access_token_expires
        )
        
        logger.info(f"User logged in: {user_data.email}")
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/me", response_model=User)
async def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user information"""
    try:
        user = await get_current_user(credentials.credentials)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return User(**user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/logout")
async def logout():
    """Logout user (client-side token removal)"""
    return {"message": "Successfully logged out"}
