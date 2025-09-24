import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
load_dotenv()

class Settings(BaseSettings):
    
    # Database configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")

    # OpenAI configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # LLM configuration
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.3"))
    TOP_K: int = int(os.getenv("TOP_K", "6"))
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    NLP_LLM_MODEL: str = os.getenv("NLP_LLM_MODEL", "gpt-4o")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # CORS configuration
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://retail-ai-chatbot.vercel.app")

    # For production deployment (Railway/Vercel)
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    PORT: int = int(os.getenv("PORT", "8000"))
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")

    # LLM Configuration
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # File Storage
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB

    # Purchase Order Settings
    PO_APPROVAL_THRESHOLD: float = float(os.getenv("PO_APPROVAL_THRESHOLD", "50000.0"))

    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.example.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "your-email@example.com")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "your-email-password")
    # SendGrid Configuration
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    SENDGRID_FROM_EMAIL: str = os.getenv("SENDGRID_FROM_EMAIL", "noreply@yourcompany.com")

    # Template IDs (you'll get these from SendGrid dashboard)
    SENDGRID_PO_APPROVAL_TEMPLATE_ID: str = os.getenv("SENDGRID_PO_APPROVAL_TEMPLATE_ID", "")
    SENDGRID_PO_VENDOR_TEMPLATE_ID: str = os.getenv("SENDGRID_PO_VENDOR_TEMPLATE_ID", "")
    SENDGRID_PO_STATUS_TEMPLATE_ID: str = os.getenv("SENDGRID_PO_STATUS_TEMPLATE_ID", "")

    COMPANY_NAME: str = os.getenv("COMPANY_NAME", "Your Company Name")
    COMPANY_ADDRESS: str = os.getenv("COMPANY_ADDRESS", "Your Company Address")
    COMPANY_PHONE: str = os.getenv("COMPANY_PHONE", "Your Company Phone")
    COMPANY_EMAIL: str = os.getenv("COMPANY_EMAIL", "Your Company Email")
    COMPANY_WEBSITE: str = os.getenv("COMPANY_WEBSITE", "Your Company Website")
    COMPANY_CONTACT_NAME: str = os.getenv("COMPANY_CONTACT_NAME", "Your Company Contact Name")

    # CORS
    ALLOWED_ORIGINS: list = [
        "http://localhost:3000",
        "https://retail-ai-chatbot.vercel.app"
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

settings = Settings()
