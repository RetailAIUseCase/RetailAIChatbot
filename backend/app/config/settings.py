from typing import List, Optional
from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings
# from dotenv import load_dotenv
# load_dotenv()

class Settings(BaseSettings):
    
    # Database configuration
    DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_ANON_KEY: str

    # OpenAI configuration
    OPENAI_API_KEY: str

    # LLM configuration
    SIMILARITY_THRESHOLD: float
    TOP_K: int
    EMBED_MODEL: str 
    LLM_MODEL: str
    NLP_LLM_MODEL: str 
    EMBEDDING_DIMENSIONS: int

    # Security
    SECRET_KEY: str 
    ALGORITHM: str 
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    
    # CORS configuration
    FRONTEND_URL: str 

    # For production deployment (Railway/Vercel)
    ENVIRONMENT: str
    PORT: int 
    API_BASE_URL: str 

    # File Storage
    # UPLOAD_DIR: str = "uploads"
    # MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB 

    # Purchase Order Settings
    PO_APPROVAL_THRESHOLD: float 

    SMTP_SERVER: str 
    SMTP_PORT: int 
    SMTP_USERNAME: str 
    SMTP_PASSWORD: str
    # SendGrid Configuration
    SENDGRID_API_KEY: str
    SENDGRID_FROM_EMAIL: str 
    EMAIL_PROVIDER: str

    # Template IDs (you'll get these from SendGrid dashboard)
    SENDGRID_PO_APPROVAL_TEMPLATE_ID: str 
    SENDGRID_PO_VENDOR_TEMPLATE_ID: str 
    SENDGRID_PO_STATUS_TEMPLATE_ID: str

    COMPANY_NAME: str 
    COMPANY_ADDRESS: str 
    COMPANY_PHONE: str 
    COMPANY_EMAIL: str
    COMPANY_WEBSITE: str 
    COMPANY_CONTACT_NAME: str

    # CORS
    ALLOWED_ORIGINS: List[str] = []

    @field_validator("ALLOWED_ORIGINS", mode="before")
    def set_allowed_origins(cls, v, info: ValidationInfo):
        frontend_url = info.data.get("FRONTEND_URL", "https://scia-chatbot.vercel.app")
        return [
            "http://localhost:3000",
            frontend_url,
        ]

    
    def validate_settings(self) -> bool:
        """Validate that required settings are present"""
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is required")
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY environment variable is required and should be secure")
        if not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        return True
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()
