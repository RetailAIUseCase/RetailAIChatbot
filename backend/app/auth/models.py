"""
Pydantic models for authentication
"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    """Base user model"""
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    """User creation model"""
    password: str

class UserLogin(BaseModel):
    """User login model"""
    email: EmailStr
    password: str

class User(UserBase):
    """User response model"""
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    """Token response model"""
    access_token: str
    token_type: str
    expires_in: int

class TokenData(BaseModel):
    """Token data model"""
    email: Optional[str] = None
