"""
Authentication utilities
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
import bcrypt
from jose import JWTError, jwt
from app.config.settings import settings
from app.database.connection import db
import logging

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    # return pwd_context.verify(plain_password, hashed_password)
    # Check password length (bcrypt limit) but be more lenient
    try:
        password_bytes = plain_password.encode('utf-8')
        if len(password_bytes) > 72:
            logger.warning(f"Password length {len(password_bytes)} bytes, truncating to 72")
            password_bytes = password_bytes[:72]
        
        hashed_bytes = hashed_password.encode('utf-8')
        result = bcrypt.checkpw(password_bytes, hashed_bytes)
        logger.debug(f"Password verification result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

def get_password_hash(password: str) -> str:
    """Get password hash"""
    # return pwd_context.hash(password)
    try:
        # Handle long passwords by truncating (bcrypt limitation)
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            logger.warning(f"Password length {len(password_bytes)} bytes, truncating to 72")
            password_bytes = password_bytes[:72]
        
        # Generate salt and hash
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')
        
    except Exception as e:
        logger.error(f"Password hashing error: {e}")
        raise ValueError(f"Password hashing failed: {str(e)}")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    try:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
        
    except Exception as e:
        logger.error(f"Token creation error: {e}")
        raise ValueError(f"Token creation failed: {str(e)}")

async def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user with email and password"""
    try:
        logger.info(f"Authentication attempt for: {email}")
        
        user = await db.get_user_by_email(email)
        if not user:
            logger.warning(f"User not found: {email}")
            return None
        
        logger.debug(f"User found, verifying password for: {email}")
        password_valid = verify_password(password, user["hashed_password"])
        
        if not password_valid:
            logger.warning(f"Invalid password for: {email}")
            return None
        
        logger.info(f"Authentication successful for: {email}")
        return user
        
    except Exception as e:
        logger.error(f"Authentication error for {email}: {e}")
        return None

async def get_current_user(token: str) -> Optional[Dict[str, Any]]:
    """Get current user from JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            logger.warning("Token missing email subject")
            return None
        
        user = await db.get_user_by_email(email)
        if not user:
            logger.warning(f"User not found for token: {email}")
            return None
            
        return user
        
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        return None
