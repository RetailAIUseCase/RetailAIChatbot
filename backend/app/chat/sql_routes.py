"""
SQL Chat routes for RAG-powered database querying
"""
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.utils.auth_utils import get_current_user
from app.config.settings import settings
from app.services.rag_sql_service import rag_sql_service
from app.database.connection import db
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["sql-chat"])
security = HTTPBearer()

class SQLChatRequest(BaseModel):
    message: str
    project_id: str
    conversation_id: Optional[str] = None

class SQLChatResponse(BaseModel):
    conversation_id: str
    intent: str
    sql_query: Optional[str] = None
    explanation: str
    tables_used: Optional[List[str]] = None
    business_rules_applied: Optional[List[str]] = None  # New field
    reference_context: Optional[List[str]] = None      # New field
    query_result: Optional[Dict[str, Any]] = None
    final_answer: str
    confidence: float
    sample_data: Optional[List[Dict]] = None  # Add this field
    total_rows: Optional[int] = None          # Add this field
    # Enhanced metadata fields
    retrieval_stats: Optional[Dict[str, int]] = None   # New field for retrieval statistics
    context_sources: Optional[List[str]] = None       # New field for context source types

    po_workflow: Optional[Dict[str, Any]] = None  # PO workflow details
    po_suggestion: Optional[Dict[str, Any]] = None  # PO suggestions from SQL results

@router.post("/query", response_model=SQLChatResponse)
async def chat_with_database(
    chat_request: SQLChatRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Chat with database using natural language"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Create embedding for user query
        query_embedding = await rag_sql_service.embed_query(chat_request.message)
        
        # Retrieve relevant tables and components
        relevant_data = await rag_sql_service.retrieve_relevant_data(
            query_embedding, 
            user_id=user["id"],
            project_id=chat_request.project_id,
            top_k=settings.TOP_K,
            similarity_threshold=settings.SIMILARITY_THRESHOLD
        )
        # Generate SQL response
        response = await rag_sql_service.process_user_query(
            user_query=chat_request.message,
            relevant_data=relevant_data,
            user_id=user["id"],
            project_id=chat_request.project_id
        )
        # sample_data = None
        # total_rows = None
        # if response.get("query_result") and response["query_result"].get("success"):
        #     data = response["query_result"]["data"]
        #     if len(data) > 10:
        #         # Limit sample data to first 10 rows for preview
        #         sample_data = data[:10]  # First 10 rows for preview
        #     else:
        #         sample_data = data
        #     total_rows = len(data)
        # Prepare retrieval statistics
        # retrieval_stats = {
        #     "total_results": relevant_data.get("total_results", 0),
        #     "metadata_results": len(relevant_data.get("metadata", [])),
        #     "business_logic_results": len(relevant_data.get("business_logic", [])),
        #     "reference_results": len(relevant_data.get("references", []))
        # }
        
        # Determine context sources used
        context_sources = []
        if relevant_data.get("metadata"):
            context_sources.append("database_schema")
        if relevant_data.get("business_logic"):
            context_sources.append("business_rules")
        if relevant_data.get("references"):
            context_sources.append("documentation")
        
        return SQLChatResponse(
            conversation_id=chat_request.conversation_id or f"{user['id']}_{chat_request.project_id}",
            intent=response.get("intent", "general_question"),
            sql_query=response.get("sql_query"),
            explanation=response.get("explanation", ""),
            tables_used=response.get("tables_used", []),
            business_rules_applied=response.get("business_rules_applied", []),
            reference_context=response.get("reference_context", []),
            query_result=response.get("query_result"),
            final_answer=response.get("final_answer", response.get("explanation", "")),
            confidence=response.get("confidence", 0.8),
            sample_data=response.get("sample_data",[]),
            total_rows=response.get("total_rows",0),
            # retrieval_stats=retrieval_stats,
            # context_sources=context_sources,
            po_workflow=response.get("po_workflow"),     
            po_suggestion=response.get("po_suggestion")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SQL chat error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/conversations/{project_id}")
async def get_project_conversations(
    project_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all conversations for a project"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")

        conversations = await db.get_user_conversations(user["id"], project_id)
        return {"conversations": conversations}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get conversations error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/conversation/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all messages for a specific conversation"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")

        messages = await db.get_conversation_messages(conversation_id, user["id"])
        return {"messages": messages}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get conversation messages error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Delete a conversation and all its messages"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")

        # Delete conversation (messages will be deleted via CASCADE)
        deleted = await db.delete_conversation(conversation_id, user["id"])
        
        if deleted:
            return {"message": "Conversation deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Conversation not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete conversation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    
# Additional endpoints for enhanced functionality

@router.get("/context-stats/{project_id}")
async def get_context_statistics(
    project_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get statistics about available context for a project"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Get a dummy embedding to test retrieval capabilities
        test_embedding = await rag_sql_service.embed_query("test query for statistics")
        
        # Get comprehensive stats
        context_data = await rag_sql_service.retrieve_relevant_data(
            test_embedding,
            user_id=user["id"],
            project_id=project_id,
            top_k=100,  # Get more data for stats
            similarity_threshold=0.0  # Include everything
        )
        
        return {
            "project_id": project_id,
            "total_metadata_embeddings": len(context_data.get("metadata", [])),
            "total_business_rules": len(context_data.get("business_logic", [])),
            "total_reference_chunks": len(context_data.get("references", [])),
            "available_tables": list(set(
                item.get("table_name") for item in context_data.get("metadata", [])
                if item.get("table_name")
            )),
            "context_readiness": {
                "has_schema": len(context_data.get("metadata", [])) > 0,
                "has_business_rules": len(context_data.get("business_logic", [])) > 0,
                "has_documentation": len(context_data.get("references", [])) > 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get context stats error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/explain-context")
async def explain_query_context(
    chat_request: SQLChatRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Explain what context would be used for a query without executing it"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Create embedding for user query
        query_embedding = await rag_sql_service.embed_query(chat_request.message)
        
        # Retrieve relevant data
        relevant_data = await rag_sql_service.retrieve_relevant_data(
            query_embedding,
            user_id=user["id"],
            project_id=chat_request.project_id,
            top_k=10
        )
        
        # Format explanation
        explanation = {
            "query": chat_request.message,
            "metadata_context": [
                {
                    "table": item.get("table_name"),
                    "type": item.get("content_type"),
                    "similarity": item.get("similarity"),
                    "content_preview": item.get("content", "")[:200] + "..."
                }
                for item in relevant_data.get("metadata", [])[:5]
            ],
            "business_rules_context": [
                {
                    "rule_number": item.get("rule_number"),
                    "similarity": item.get("similarity"),
                    "content_preview": item.get("content", "")[:200] + "..."
                }
                for item in relevant_data.get("business_logic", [])[:3]
            ],
            "reference_context": [
                {
                    "chunk_index": item.get("chunk_index"),
                    "similarity": item.get("similarity"),
                    "content_preview": item.get("content", "")[:200] + "..."
                }
                for item in relevant_data.get("references", [])[:3]
            ],
            "retrieval_stats": {
                "total_results": relevant_data.get("total_results", 0),
                "metadata_count": len(relevant_data.get("metadata", [])),
                "business_logic_count": len(relevant_data.get("business_logic", [])),
                "reference_count": len(relevant_data.get("references", []))
            }
        }
        
        return explanation
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explain context error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Health check for RAG service
@router.get("/health")
async def health_check():
    """Check if the RAG SQL service is healthy"""
    try:
        # Test embedding creation
        test_embedding = await rag_sql_service.embed_query("test health check")
        
        return {
            "status": "healthy",
            "embedding_service": "operational",
            "embedding_dimensions": len(test_embedding),
            "po_generation_enabled": True,
            "date_parser_enabled": hasattr(rag_sql_service, 'date_parser'),
            "conversation_memory_active": len(rag_sql_service.conversation_memory) > 0
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

# Endpoint for testing PO functionality
@router.post("/test-po")
async def test_po_generation(
    chat_request: SQLChatRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Test PO generation functionality"""
    try:
        user = await get_current_user(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Test PO intent detection
        intent = await rag_sql_service.detect_query_intent(chat_request.message, [])
        
        if intent == "po_generation":
            # Test date extraction
            extracted_date = await rag_sql_service.extract_date_from_query_llm(chat_request.message)
            parsed_date = await rag_sql_service.date_parser.parse_date_llm(extracted_date)
            
            return {
                "message": chat_request.message,
                "detected_intent": intent,
                "extracted_date": extracted_date,
                "parsed_date": parsed_date,
                "po_generation_ready": True
            }
        else:
            return {
                "message": chat_request.message,
                "detected_intent": intent,
                "po_generation_ready": False,
                "reason": "Not a PO generation query"
            }
            
    except Exception as e:
        logger.error(f"PO test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
