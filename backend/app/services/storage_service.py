"""
Storage Service using Supabase Storage with actual file operations
"""

import os
import uuid
import httpx
from typing import Dict, Any
from fastapi import UploadFile, HTTPException
import mimetypes
import logging
import asyncpg
from app.config.settings import settings

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        # We'll use direct SQL queries to interact with Supabase Storage
        self.buckets = {
            "metadata": "metadata-documents",
            "businesslogic": "business-logic-documents",
            "references": "reference-documents"
        }
        
        # Supabase configuration
        self.supabase_url = settings.SUPABASE_URL  
        self.supabase_service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY  
        self.supabase_anon_key = settings.SUPABASE_ANON_KEY  

    async def upload_file(self, file: UploadFile, user_id: int, project_id: str, document_type: str) -> Dict[str, Any]:
        """Upload file to appropriate Supabase Storage bucket"""
        try:
            # Select bucket based on document type
            bucket_name = self.buckets.get(document_type)
            if not bucket_name:
                raise ValueError(f"Invalid document type: {document_type}")

            # Generate unique filename
            file_extension = os.path.splitext(file.filename)[1] if file.filename else ""
            unique_filename = f"{uuid.uuid4()}{file_extension}"

            # Create file path: user_id/project_id/unique_filename
            file_path = f"{user_id}/{project_id}/{unique_filename}"

            # Read file content
            file_content = await file.read()

            # Store file using Supabase Storage REST API
            await self._store_file_in_bucket(bucket_name, file_path, file_content, file.content_type)

            return {
                "file_path": file_path,
                "bucket_name": bucket_name,
                "original_filename": file.filename,
                "file_size": len(file_content),
                "content_type": file.content_type
            }

        except Exception as e:
            logger.error(f"File upload error: {e}")
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    async def _store_file_in_bucket(self, bucket_name: str, file_path: str, file_content: bytes, content_type: str):
        """Store file in Supabase Storage bucket using REST API"""
        try:
            async with httpx.AsyncClient() as client:
                # Upload file to Supabase Storage
                upload_url = f"{self.supabase_url}/storage/v1/object/{bucket_name}/{file_path}"
                
                headers = {
                    "Authorization": f"Bearer {self.supabase_service_role_key}",
                    "Content-Type": content_type or "application/octet-stream"
                }
                
                response = await client.post(
                    upload_url,
                    content=file_content,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code not in [200, 201]:
                    error_text = response.text
                    logger.error(f"Supabase upload failed: {response.status_code} - {error_text}")
                    raise Exception(f"Upload failed: {error_text}")
                
                logger.info(f"File uploaded successfully to {bucket_name}/{file_path}")
                
        except Exception as e:
            logger.error(f"Error storing file in bucket: {e}")
            raise

    async def download_file(self, bucket_name: str, file_path: str) -> bytes:
        """Download file from Supabase Storage bucket"""
        try:
            async with httpx.AsyncClient() as client:
                # Download file from Supabase Storage
                download_url = f"{self.supabase_url}/storage/v1/object/{bucket_name}/{file_path}"
                
                headers = {
                    "Authorization": f"Bearer {self.supabase_service_role_key}",
                }
                
                response = await client.get(
                    download_url,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"File downloaded successfully from {bucket_name}/{file_path}")
                    return response.content
                elif response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"File not found: {bucket_name}/{file_path}")
                else:
                    error_text = response.text
                    logger.error(f"Supabase download failed: {response.status_code} - {error_text}")
                    raise Exception(f"Download failed: {error_text}")
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"File download error: {e}")
            raise HTTPException(status_code=500, detail=f"File download failed: {str(e)}")

    async def create_buckets_if_not_exist(self):
        """Create storage buckets if they don't exist"""
        try:
            async with httpx.AsyncClient() as client:
                for document_type, bucket_name in self.buckets.items():
                    # Check if bucket exists
                    list_url = f"{self.supabase_url}/storage/v1/bucket"
                    
                    headers = {
                        "Authorization": f"Bearer {self.supabase_service_role_key}",
                        "Content-Type": "application/json"
                    }
                    
                    # List buckets to check if it exists
                    response = await client.get(list_url, headers=headers)
                    
                    if response.status_code == 200:
                        buckets = response.json()
                        bucket_exists = any(bucket["id"] == bucket_name for bucket in buckets)
                        
                        if not bucket_exists:
                            # Create bucket
                            create_url = f"{self.supabase_url}/storage/v1/bucket"
                            bucket_data = {
                                "id": bucket_name,
                                "name": bucket_name,
                                "public": False,  # Keep private for security
                                "file_size_limit": 52428800,  # 50MB
                                "allowed_mime_types": [
                                    "application/pdf",
                                    "application/msword",
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    "text/plain",
                                    "application/json",
                                    "text/csv",
                                    "text/markdown",
                                    "text/html"
                                ]
                            }
                            
                            create_response = await client.post(
                                create_url,
                                json=bucket_data,
                                headers=headers
                            )
                            
                            if create_response.status_code in [200, 201]:
                                logger.info(f"Created bucket: {bucket_name}")
                            else:
                                logger.error(f"Failed to create bucket {bucket_name}: {create_response.text}")
                        else:
                            logger.info(f"Bucket {bucket_name} already exists")
                    else:
                        logger.error(f"Failed to list buckets: {response.text}")
                        
        except Exception as e:
            logger.error(f"Error creating buckets: {e}")

    async def delete_file(self, bucket_name: str, file_path: str) -> bool:
        """Delete file from Supabase Storage bucket"""
        try:
            async with httpx.AsyncClient() as client:
                delete_url = f"{self.supabase_url}/storage/v1/object/{bucket_name}/{file_path}"
                
                headers = {
                    "Authorization": f"Bearer {self.supabase_service_role_key}",
                }
                
                response = await client.delete(delete_url, headers=headers)
                
                if response.status_code in [200, 204]:
                    logger.info(f"File deleted successfully: {bucket_name}/{file_path}")
                    return True
                elif response.status_code == 404:
                    logger.warning(f"File not found for deletion: {bucket_name}/{file_path}")
                    return False
                else:
                    logger.error(f"Failed to delete file: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"File deletion error: {e}")
            return False

    async def get_file_info(self, bucket_name: str, file_path: str) -> Dict[str, Any]:
        """Get file information from Supabase Storage"""
        try:
            async with httpx.AsyncClient() as client:
                info_url = f"{self.supabase_url}/storage/v1/object/info/{bucket_name}/{file_path}"
                
                headers = {
                    "Authorization": f"Bearer {self.supabase_service_role_key}",
                }
                
                response = await client.get(info_url, headers=headers)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    raise HTTPException(status_code=404, detail="File not found")
                else:
                    raise Exception(f"Failed to get file info: {response.text}")
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"File info error: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get file info: {str(e)}")

# Global instance
storage_service = StorageService()
