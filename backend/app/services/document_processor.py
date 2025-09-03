"""
Enhanced Document Processor with hash-based deduplication
"""
import asyncio
from datetime import datetime
import os
import re
import json
from typing import List, Dict, Any
import logging
from openai import AsyncOpenAI
import PyPDF2
import docx
from io import BytesIO
from docx import Document
from app.config.settings import settings
from app.services.storage_service import storage_service
from app.database.connection import db
from app.utils.document_parsers import MetadataParser, BusinessLogicParser, ReferenceParser, FileExtractor


logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self):
        self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.embed_model = settings.EMBED_MODEL
        self.embedding_dimensions = settings.EMBEDDING_DIMENSIONS

        # Initialize parsers
        self.metadata_parser = MetadataParser()
        self.business_logic_parser = BusinessLogicParser()
        self.reference_parser = ReferenceParser()
        self.file_extractor = FileExtractor()

        # Define processing strategies per document type
        self.processing_strategies = {
            "metadata": self._create_metadata_embeddings,
            "businesslogic": self._create_business_logic_embeddings,
            "references": self._create_reference_embeddings
        }

    # Add progress update method
    async def _update_processing_progress(self, document_id: str, progress: int, status: str, details: str = ""):
        """Update processing progress with detailed status"""
        if not db.pool:
            return
        
        try:
            processing_info = {
                "progress": progress,
                "details": details,
                "updated_at": datetime.now().isoformat(),
                "stage": self._get_processing_stage(progress)
            }
            
            async with db.pool.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE documents 
                    SET embedding_status = $1, 
                        updated_at = CURRENT_TIMESTAMP,
                        processing_details = $3
                    WHERE id = $2
                    """,
                    status, document_id, json.dumps(processing_info)
                )
            logger.info(f"Updated document {document_id}: {status} ({progress}%) - {details}")
        except Exception as e:
            logger.error(f"Error updating processing progress for {document_id}: {e}")

    def _get_processing_stage(self, progress: int) -> str:
        """Get processing stage based on progress"""
        if progress < 20:
            return "initializing"
        elif progress < 40:
            return "extracting_text"
        elif progress < 80:
            return "creating_embeddings"
        elif progress < 100:
            return "finalizing"
        else:
            return "complete"
    async def process_document(self, document_id: str, file_path: str, document_type: str, bucket_name: str) -> Dict[str, Any]:
        """Process document with bucket-specific logic"""
        try:

            await self._update_processing_progress(document_id, 10, "processing", "Starting document processing")

            # Get document info including user_id and project_id
            document_info = await self._get_document_info(document_id)
            if not document_info:
                raise Exception("Document not found")
            
            user_id = document_info['user_id']
            project_id = document_info['project_id']
            
            await self._update_processing_progress(document_id, 30, "processing", "Extracting text content")

            # Download file from specific bucket
            file_content = await storage_service.download_file(bucket_name, file_path)
            
            # Extract text
            text_content = await self._extract_text(file_content, file_path)

            await self._update_processing_progress(document_id, 60, "processing", "Creating embeddings")

            # Use type-specific processing strategy with deduplication
            if document_type in self.processing_strategies:
                stats = await self.processing_strategies[document_type](
                    text_content, document_id, user_id, project_id
                )
            else:
                raise ValueError(f"Unsupported document type: {document_type}")
            
            await self._update_processing_progress(document_id, 100, "completed", "Processing complete")
            # Update document status
            # await self._update_document_status(document_id, "completed")
            
            return {
                "success": True,
                "stats": stats,
                "document_id": document_id,
                "bucket_name": bucket_name
            }
            
        except Exception as e:
            logger.error(f"Document processing error: {e}")
            await self._update_processing_progress(document_id, 0, "failed", f"Error: {str(e)}")
            # await self._update_document_status(document_id, "failed")
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id
            }

    async def _get_document_info(self, document_id: str) -> Dict[str, Any]:
        """Get document info including user_id and project_id"""
        if not db.pool:
            raise Exception("Database pool not initialized")
            
        query = "SELECT user_id, project_id::text FROM documents WHERE id = $1"
        try:
            async with db.pool.acquire() as connection:
                row = await connection.fetchrow(query, document_id)
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get document info: {e}")
            raise
    
    async def _extract_text(self, file_content: bytes, file_path: str) -> str:
        """Extract text using FileExtractor"""
        return await self.file_extractor.extract_text(file_content, file_path)
    
    async def _create_metadata_embeddings(self, text: str, document_id: str, user_id: int, project_id: str) -> Dict[str, int]:
        """Create hierarchical embeddings for metadata documents with deduplication"""
        # Detect if it's JSON or DOCX format
        if self.metadata_parser.is_json_content(text):
            tables = self.metadata_parser.parse_json_metadata(text)
        else:
            tables = self.metadata_parser.parse_docx_metadata(text)

        # Use the deduplication method from utils
        async with db.pool.acquire() as connection:
            await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
            
            stats = await self.metadata_parser.create_embeddings_with_dedup(
                connection, tables, document_id, user_id, project_id, self._get_embedding
            )
            
            logger.info(f"Metadata processing stats for doc {document_id}: {stats}")
            return stats
    
    async def _create_business_logic_embeddings(self, text: str, document_id: str, user_id: int, project_id: str) -> Dict[str, int]:
        """Create embeddings for business logic documents with deduplication"""
        rules = self.business_logic_parser.extract_business_rules(text)
        
        # Use the deduplication method from utils
        async with db.pool.acquire() as connection:
            await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
            
            stats = await self.business_logic_parser.create_embeddings_with_dedup(
                connection, rules, document_id, user_id, project_id, self._get_embedding
            )
            
            logger.info(f"Business logic processing stats for doc {document_id}: {stats}")
            return stats
    
    async def _create_reference_embeddings(self, text: str, document_id: str, user_id: int, project_id: str) -> Dict[str, int]:
        """Create embeddings for reference documents with deduplication"""
        chunks = self.reference_parser.split_text_into_chunks(text)
        
        # Use the deduplication method from utils
        async with db.pool.acquire() as connection:
            await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
            
            stats = await self.reference_parser.create_embeddings_with_dedup(
                connection, chunks, document_id, user_id, project_id, self._get_embedding
            )
            
            logger.info(f"Reference processing stats for doc {document_id}: {stats}")
            return stats

    # Alternative batch processing method for large reference documents
    async def _create_reference_embeddings_batch(
        self, text: str, document_id: str, user_id: int, project_id: str
    ) -> Dict[str, int]:
        """Create reference embeddings using batch processing for large documents"""
        chunks = self.reference_parser.split_text_into_chunks(text)
        embeddings_batch = []
        
        # Generate all embeddings first
        for chunk_idx, chunk_text in enumerate(chunks):
            if chunk_text.strip() and len(chunk_text.strip()) > 50:
                try:
                    embedding = await self._get_embedding(chunk_text)
                    embeddings_batch.append({
                        'document_id': document_id,
                        'project_id': project_id,
                        'user_id': user_id,
                        'chunk_index': chunk_idx,
                        'content': chunk_text.strip(),
                        'embedding': embedding,
                        'metadata': {
                            "chunk_index": chunk_idx,
                            "chunk_type": "reference_content",
                            "word_count": len(chunk_text.split()),
                            "content_hash": self.reference_parser.generate_content_hash(chunk_text)
                        }
                    })
                except Exception as e:
                    logger.error(f"Error creating embedding for chunk {chunk_idx}: {e}")
        
        # Batch insert all embeddings
        if embeddings_batch:
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                inserted_count = await self.reference_parser.batch_insert_reference_embeddings(
                    connection, embeddings_batch
                )
                logger.info(f"Batch inserted {inserted_count} reference embeddings")
                return {"inserted": inserted_count, "updated": 0, "skipped": 0}
        
        return {"inserted": 0, "updated": 0, "skipped": 0}
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Create embedding using OpenAI"""
        for attempt in range(3):
            try:
                response = await self.openai_client.embeddings.create(
                    model=self.embed_model,
                    input=text.strip(),
                    dimensions=self.embedding_dimensions
                )
                return response.data[0].embedding
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(1)
                else:
                    logger.error(f"Failed to get embedding: {e}")
                    raise RuntimeError(f"Failed to get embedding: {e}")

    # async def _update_document_status(self, document_id: str, status: str):
    #     """Update document processing status"""
    #     if not db.pool:
    #         return
            
    #     try:
    #         async with db.pool.acquire() as connection:
    #             await connection.execute(
    #                 "UPDATE documents SET embedding_status = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
    #                 status, document_id
    #             )
    #     except Exception as e:
    #         logger.error(f"Error updating document status: {e}")

    # Utility methods for batch processing and monitoring
    async def process_documents_batch(
        self, 
        document_batch: List[Dict[str, str]], 
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """Process multiple documents concurrently with rate limiting"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(doc_info):
            async with semaphore:
                return await self.process_document(
                    doc_info["document_id"],
                    doc_info["file_path"],
                    doc_info["document_type"],
                    doc_info["bucket_name"]
                )
        
        tasks = [process_with_semaphore(doc_info) for doc_info in document_batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing document {document_batch[i]['document_id']}: {result}")
                processed_results.append({
                    "success": False,
                    "error": str(result),
                    "document_id": document_batch[i]["document_id"]
                })
            else:
                processed_results.append(result)
        
        return processed_results

    async def get_processing_statistics(self, project_id: str, user_id: int) -> Dict[str, Any]:
        """Get processing statistics for a project"""
        if not db.pool:
            raise Exception("Database pool not initialized")
        
        stats_query = """
        WITH document_stats AS (
            SELECT 
                document_type,
                embedding_status,
                COUNT(*) as count
            FROM documents 
            WHERE project_id = $1 AND user_id = $2
            GROUP BY document_type, embedding_status
        ),
        embedding_stats AS (
            SELECT 'metadata' as type, COUNT(*) as embeddings_count FROM metadata_embeddings WHERE project_id = $1 AND user_id = $2
            UNION ALL
            SELECT 'businesslogic' as type, COUNT(*) as embeddings_count FROM business_logic_embeddings WHERE project_id = $1 AND user_id = $2
            UNION ALL
            SELECT 'references' as type, COUNT(*) as embeddings_count FROM reference_embeddings WHERE project_id = $1 AND user_id = $2
        )
        SELECT 
            json_build_object(
                'documents', json_agg(json_build_object('type', document_type, 'status', embedding_status, 'count', count)),
                'embeddings', (SELECT json_agg(json_build_object('type', type, 'count', embeddings_count)) FROM embedding_stats)
            ) as stats
        FROM document_stats
        """
        
        try:
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                row = await connection.fetchrow(stats_query, project_id, user_id)
                return row['stats'] if row else {"documents": [], "embeddings": []}
        except Exception as e:
            logger.error(f"Error getting processing statistics: {e}")
            return {"documents": [], "embeddings": []}

    async def reprocess_failed_documents(self, project_id: str, user_id: int) -> List[Dict[str, Any]]:
        """Reprocess all failed documents for a project"""
        if not db.pool:
            raise Exception("Database pool not initialized")
        
        # Get failed documents
        query = """
        SELECT id::text as document_id, file_path, document_type, bucket_name
        FROM documents 
        WHERE project_id = $1 AND user_id = $2 AND embedding_status = 'failed'
        """
        
        try:
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                rows = await connection.fetch(query, project_id, user_id)
                
                failed_docs = [dict(row) for row in rows]
                
                if failed_docs:
                    logger.info(f"Reprocessing {len(failed_docs)} failed documents for project {project_id}")
                    results = await self.process_documents_batch(failed_docs, max_concurrent=2)
                    return results
                else:
                    logger.info(f"No failed documents found for project {project_id}")
                    return []
                
        except Exception as e:
            logger.error(f"Error reprocessing failed documents: {e}")
            return []

# Global instance
document_processor = DocumentProcessor()
