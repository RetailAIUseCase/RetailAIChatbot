import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
load_dotenv()

class Settings(BaseSettings):
    # # Database
    # SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    # SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    # DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
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

    # LLM Configuration
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    
    # File Storage
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    
    # Vector Database
    PINECONE_API_KEY: Optional[str] = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "rag-documents")
    
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
