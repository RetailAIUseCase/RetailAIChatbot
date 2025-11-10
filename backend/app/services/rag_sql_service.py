"""
RAG SQL Service for natural language to SQL conversion
"""
import asyncio
import json
import re
from typing import Dict, List, Any, Optional, Tuple
import uuid
from openai import AsyncOpenAI
from datetime import datetime
from app.database.connection import db
from app.config.settings import settings
from app.utils.date_parser import parse_user_date_safe
from app.services.po_workflow_service import po_workflow_service
# from app.services.enhanced_intelligent_po_service_combined import enhanced_intelligent_po_service_combined
from app.services.visualization_service import chart_service
import logging

from app.utils.date_parser_llm import LLMDateParser

logger = logging.getLogger(__name__)

class SQLRAGService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        # self.conversation_memory = {}  # Store conversation history
        self.Embedding_model = settings.EMBED_MODEL
        self.LLM_model = settings.LLM_MODEL
        self.NLP_LLM_model = settings.NLP_LLM_MODEL
        self.embedding_dimensions = settings.EMBEDDING_DIMENSIONS
        self.date_parser = LLMDateParser(self.client, self.NLP_LLM_model)

    async def embed_query(self, query: str) -> List[float]:
        """Create embedding for user query"""
        try:
            response = await self.client.embeddings.create(
                model=self.Embedding_model,
                input=query.strip(),
                dimensions=self.embedding_dimensions
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error creating embedding: {e}")
            raise
    async def retrieve_relevant_data(
        self, 
        query_embedding: List[float], 
        user_id: int, 
        project_id: str,
        top_k: int, 
        similarity_threshold: float
    ) -> Dict[str, Any]:
        """Enhanced retrieval from multiple embedding tables"""
        if not db.pool:
            raise Exception("Database pool not initialized")
        
        try:
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                # Phase 1: Retrieve from metadata embeddings (tables, columns, relationships)
                metadata_results = await self._retrieve_metadata_embeddings(
                    connection, query_embedding, user_id, project_id, top_k, similarity_threshold
                )
                # print(metadata_results)

                # Phase 2: Retrieve from business logic embeddings  
                business_logic_results = await self._retrieve_business_logic_embeddings(
                    connection, query_embedding, user_id, project_id, top_k//2, similarity_threshold
                )
                
                # Phase 3: Retrieve from reference embeddings
                reference_results = await self._retrieve_reference_embeddings(
                    connection, query_embedding, user_id, project_id, top_k, similarity_threshold
                )
                
                return {
                    "metadata": metadata_results,
                    "business_logic": business_logic_results, 
                    "references": reference_results,
                    "total_results": len(metadata_results) + len(business_logic_results) + len(reference_results)
                }
                
        except Exception as e:
            logger.error(f"Error retrieving schemas: {e}")
            return {
                "error": f"Retrieval failed: {str(e)}", 
                "metadata": [], 
                "business_logic": [],
                "references": [],
                "total_results": 0
            }
        

    async def _retrieve_metadata_embeddings(
        self, connection, query_embedding: List[float], user_id: int, project_id: str, top_k: int, similarity_threshold: float
    ) -> List[Dict]:
        """Retrieve from metadata embeddings with hierarchical approach"""
        # Convert embedding list to pgvector format
        # embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        # First get table-level embeddings
        table_query = """
        SELECT 
            table_name,
            content_type,
            content,
            metadata,
            (embedding <=> $1) as distance,
            (1 - (embedding <=> $1)) as similarity
        FROM metadata_embeddings 
        WHERE user_id = $2 AND project_id = $3 AND content_type = 'table'
            AND (1 - (embedding <=> $1)) >= $5  -- Similarity threshold
        ORDER BY embedding <=> $1
        LIMIT $4
        """
        
        table_results = await connection.fetch(table_query, query_embedding, user_id, project_id, top_k, similarity_threshold)
        
        if not table_results:
            return []
        # Step 2: Extract related tables from foreign key relationships
        primary_tables = set(row['table_name'] for row in table_results)
        related_tables = set()
        
        for row in table_results:
            metadata = json.loads(row['metadata']) if isinstance(row['metadata'], str) else (row['metadata'] or {})
            foreign_keys = metadata.get('foreign_keys', '')
            
            if foreign_keys:
                # Extract referenced table names
                fk_patterns = re.findall(r'references\s+(\w+)', foreign_keys, re.IGNORECASE)
                related_tables.update(fk_patterns)
        
        # Step 3: Get all relevant tables (primary + related)
        all_relevant_tables = list(primary_tables.union(related_tables))
        
        # Step 4: Get complete information for all relevant tables
        complete_query = """
        SELECT 
            table_name,
            content_type,
            content,
            metadata,
            (embedding <=> $1) as distance
        FROM metadata_embeddings 
        WHERE user_id = $2 AND project_id = $3 
            AND table_name = ANY($4)
            AND content_type IN ('column', 'relationship')
        ORDER BY 
            CASE WHEN table_name = ANY($5) THEN 0 ELSE 1 END,  -- Primary tables first
            embedding <=> $1
        """
        
        detail_results = await connection.fetch(
            complete_query, query_embedding, user_id, project_id, 
            all_relevant_tables, list(primary_tables)
        )
        all_results = list(table_results) + list(detail_results)
        return [
            {
                "table_name": row['table_name'],
                "content_type": row['content_type'],
                "content": row['content'],
                "similarity": float(1 - row['distance']),
                "metadata": json.loads(row['metadata']) if isinstance(row['metadata'], str) else (row['metadata'] or {}),
                "source": "metadata",
                "is_primary": row['table_name'] in primary_tables
            } for row in all_results
        ]
        # Get top table names
        # top_tables = [row['table_name'] for row in table_results]
        
        # # Then get column and relationship embeddings for those tables
        # detail_query = """
        # SELECT 
        #     table_name,
        #     content_type,
        #     content,
        #     metadata,
        #     (embedding <=> $1) as distance
        # FROM metadata_embeddings 
        # WHERE user_id = $2 AND project_id = $3 
        #       AND table_name = ANY($4)
        #       AND content_type IN ('column', 'relationship')
        # ORDER BY embedding <=> $1
        # LIMIT $5
        # """
        # components_top_k = top_k * 4
        # detail_results = await connection.fetch(
        #     detail_query, query_embedding, user_id, project_id, top_tables, components_top_k
        # )
        
        # # Combine and format results
        # all_results = list(table_results) + list(detail_results)
        
        # return [
        #     {
        #         "table_name": row['table_name'],
        #         "content_type": row['content_type'],
        #         "content": row['content'],
        #         "similarity": float(1 - row['distance']),
        #         "metadata": json.loads(row['metadata']) if isinstance(row['metadata'], str) else (row['metadata'] or {}),
        #         "source": "metadata"
        #     } for row in all_results
        # ]

    async def _retrieve_business_logic_embeddings(
        self, connection, query_embedding: List[float], user_id: int, project_id: str, top_k: int, similarity_threshold: float
    ) -> List[Dict]:
        """Retrieve from business logic embeddings"""
        # embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        query = """
        SELECT 
            rule_number,
            content,
            metadata,
            (embedding <=> $1) as distance,
            (1 - (embedding <=> $1)) as similarity
        FROM business_logic_embeddings 
        WHERE user_id = $2 AND project_id = $3
            AND (1 - (embedding <=> $1)) >= $5  -- Similarity threshold
        ORDER BY embedding <=> $1
        LIMIT $4
        """
        results = await connection.fetch(query, query_embedding, user_id, project_id, top_k, similarity_threshold)
        # print(results)
        return [
            {
                "rule_number": row['rule_number'],
                "content": row['content'],
                "similarity": float(1 - row['distance']),
                "metadata": json.loads(row['metadata']) if isinstance(row['metadata'], str) else (row['metadata'] or {}),
                "source": "business_logic"
            } for row in results
        ]

    async def _retrieve_reference_embeddings(
        self, connection, query_embedding: List[float], user_id: int, project_id: str, top_k: int, similarity_threshold: float
    ) -> List[Dict]:
        """Retrieve from reference embeddings"""
        # embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        query = """
        SELECT 
            chunk_index,
            content,
            metadata,
            (embedding <=> $1) as distance,
            (1 - (embedding <=> $1)) as similarity
        FROM reference_embeddings 
        WHERE user_id = $2 AND project_id = $3
            AND (1 - (embedding <=> $1)) >= $5  -- Similarity threshold
        ORDER BY embedding <=> $1
        LIMIT $4
        """
        
        results = await connection.fetch(query, query_embedding, user_id, project_id, top_k, similarity_threshold)
        
        return [
            {
                "chunk_index": row['chunk_index'],
                "content": row['content'],
                "similarity": float(1 - row['distance']),
                "metadata": json.loads(row['metadata']) if isinstance(row['metadata'], str) else (row['metadata'] or {}),
                "source": "references"
            } for row in results
        ]
    
    def _build_enhanced_context(self, retrieval: Dict) -> str:
        """Build comprehensive context from all embedding sources"""
        db_context = ""
        business_context = ""
        reference_context = ""
        
        # Metadata context (tables, columns, relationships)
        if retrieval.get('metadata'):
            db_context += "DATABASE SCHEMA INFORMATION:\n"
            
            # Group and prioritize primary tables
            tables_info = {}
            primary_tables = set()
            
            for item in retrieval['metadata']:
                table_name = item['table_name']
                if item.get('is_primary', False):
                    primary_tables.add(table_name)
                    
                if table_name not in tables_info:
                    tables_info[table_name] = {'table': [], 'column': [], 'relationship': []}
                tables_info[table_name][item['content_type']].append(item)
            
            # Format primary tables first, then related tables
            for table_name in sorted(tables_info.keys(), key=lambda x: (x not in primary_tables, x)):
                table_type = "PRIMARY TABLE" if table_name in primary_tables else "RELATED TABLE"
                db_context += f"\n### {table_type}: {table_name}\n"
                
                # Clean table summary (remove assumptions/notes)
                for table_info in tables_info[table_name]['table']:
                    # clean_content = self._clean_table_content(table_info['content'])
                    db_context += f"Schema (relevance: {table_info['similarity']:.2f}):\n{table_info['content']}\n\n"
                
                # Clean column information
                for col_info in tables_info[table_name]['column']:
                    # clean_content = self._clean_column_content(col_info['content'])
                    db_context += f"Columns (relevance: {col_info['similarity']:.2f}):\n{col_info['content']}\n\n"
                
                # Clean relationship information
                for rel_info in tables_info[table_name]['relationship']:
                    # clean_content = self._clean_relationship_content(rel_info['content'])
                    db_context += f"Relationships (relevance: {rel_info['similarity']:.2f}):\n{rel_info['content']}\n\n"

        # Business logic context
        if retrieval.get('business_logic'):
            business_context += "\nBUSINESS RULES & LOGIC:\n"
            for rule in retrieval['business_logic'][:10]:  # Top 10 rules
                business_context += f"\nRule {rule['rule_number']} (similarity: {rule['similarity']:.2f}):\n{rule['content']}\n"

        # Reference context
        if retrieval.get('references'):
            reference_context += "\nREFERENCE DOCUMENTATION:\n"
            for ref in retrieval['references'][:10]:  # Top 10 references
                reference_context += f"\nReference (similarity: {ref['similarity']:.2f}):\n{ref['content']}...\n"
        
        return db_context, business_context, reference_context

    def _build_conversation_context(self, conversation_history: List[Dict], for_po: bool = False) -> str:
        """Build conversation context string"""
        context = ""
        if conversation_history:
            context = "Previous Conversation Context:\n"
            for msg in conversation_history:  # Last 6 messages
                # print(msg['intent'])
                if for_po and (msg['intent'] is None or msg['intent'] in ['visualization_complete', 'visualization_pending']):
                    continue
                if msg['role'] == 'user':
                    context += f"User: {msg['content']}\n"
                elif msg['role'] == 'assistant':
                    context += f"Assistant: {msg['content']}\n"
                    # Include the SQL query if available
                    if msg.get('sql_query'):
                        sql = msg['sql_query']
                        if len(sql) > 300:
                            sql = sql[:300] + "..."
                        context += f"(Previous SQL: {sql})\n"
                    # Include query intent
                    if msg.get('intent'):
                        context += f"Previous Intent: {msg['intent']}\n"
                    if msg.get("metadata"):
                        meta = msg["metadata"]
                        # if isinstance(meta, str):
                        #     try:
                        #         meta = json.loads(meta)
                        #     except json.JSONDecodeError:
                        #         meta = {}  # fallback in case of corrupt data
                        if "suggested_next_questions" in meta:
                            context += f"Assistant suggested: {meta['suggested_next_questions']}\n"
                        # Show chart type if generated
                        if "chart" in meta and isinstance(meta['chart'], dict):
                            chart_type = meta['chart'].get('chart_type', 'chart')
                            context += f"(Assistant generated a {chart_type})\n"
                        if "follow_up_action" in meta:
                            fa = meta["follow_up_action"]
                            context += f"Assistant executed a follow-up ({fa['action_type']}): {fa['executed_query']}\n"
                context += "\n"
        return context if len(context)>30 else ""
    
    # ======================== Intent Detection ========================== 
    async def detect_query_intent(self, user_query: str, conversation_history: List[Dict]) -> str:
        """Detect user query intent dynamically"""
        
        # Use LLM for complex cases
        context = ""
        if conversation_history:
            # recent = [msg['content'][:50] for msg in conversation_history[-3:]]
            context = self._build_conversation_context(conversation_history[-4:])
        prompt = f"""You are an intelligent assistant for supply chain management. 
    
            Analyze this user query and previous conversation context and classify it into ONE of these intents:
            *NOTE*: Always look at the previous conversation context to get better understanding of what the user query is related to, 
                    a simple "yes" can be related to any follow up resposne or can also be a confirmation to document generation or visualization conversation.

            Current User Query: "{user_query}"
            Previous conversation context: {context}
            **INTENTS:**
                1. document_generation - User wants to generate/create documents either specifying using direct keyword or indirectly (PO, invoice, reports, etc.) or based on previous conversation result, 
                                        analyse it carefully as it can be a confirmation to previous suggestion/clarification as well.
                                        It can also be a confirmation or follow up to previous conversation related to document generation
                - Keywords: "generate", "create", "make", "produce", "prepare document", "order materials", "procurement workflow"
                - Examples: "generate PO for today", "create invoice", "make inventory report"

                2. sql_query - User wants data analysis or database queries or business insights
                - Questions about data, reports, analytics, trends, counts, sums
                - Examples: "show me shortfall materials", "give me projection quantity for next month", "what's the inventory"

                3. chit_chat - Casual conversation, greetings, general questions
                - Greetings, casual talk, general questions not related to data or POs
                - Examples: "hello", "how are you", "what's the weather"

                4. clarification - User asking about capabilities or help
                - Questions about what the assistant can do
                - Examples: "what can you do", "help me", "how do I use this"
                
                5. follow_up_response - User responding to a previous follow-up question or giving or asking some clarification about previous generated answers
                - Short responses like "yes", "no", "okay", "generate it", "show me more"
                - Context-dependent responses to assistant's questions

                6. visualization - User EXPLICITLY wants to see data visualized in charts, graphs, or visual format
                    - MUST have explicit visualization requests: chart, graph, plot, visualize, visualization, display as chart/graph, show me a chart
                    - Examples: 
                        * "show me a **chart** of projection quantity"
                        * "**visualize** the trend using line graph"
                        * "**plot** stock projection"
                        * "explore the trend using a **line graph**"
                        * "show this as a **bar chart**"
                    - **NOT visualization**: "show me trend", "give me projection", "display stock levels" (these are sql_query)

                7. chart_selection - User is selecting/refining a chart type from suggestions
                    - Responses to chart type suggestions
                    - Examples: "use bar chart", "I prefer the first option"
            
            **CRITICAL RULES FOR VISUALIZATION vs SQL_QUERY:**
                - If query has words like "chart", "graph", "plot", "visualize", "visualization" → visualization
                - If query has "trend", "projection", "forecast", BUT NO chart/graph or visualization related keywords → sql_query
                - If user says "show me", "give me", "display" without chart/graph keywords → sql_query
                - Only use visualization when user EXPLICITLY requests visual representation
                - When in doubt between visualization and sql_query, choose sqlquery

            If intent doesn't fall into any of these categories, classify it by understanding the previous conversation context and return in 10-20 letters.

            Examples:
            - "Hello" → chit_chat
            - "Show me sales data" → sql_query  
            - "What can you do?" → clarification
            - "Thanks!" → chit_chat
            - "How many customers do we have?" → sql_query
            - "give me the stock projection trend" → sqlquery
            - "show me projection quantity" → sqlquery
            - "create PO for next week" → document_generation
            - "generate purchase order for tomorrow" → document_generation
            - "explore the trend of projected vs actual using a line graph" → visualization
            - "visualize the stock levels" → visualization
            - "show me a chart of inventory" → visualization

            Respond with only the intent name: document_generation, sql_query, chit_chat, clarification, follow_up_response, visualization, or chart_selection"""

        try:
            response = await self.client.chat.completions.create(
                model=self.NLP_LLM_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=10
            )
            intent = response.choices[0].message.content.strip().lower()
            # if intent == 'po_generation':
            #     # Further verify with secondary check
            #     is_po = await self._llm_verify_po_intent(user_query)
            #     return 'po_generation' if is_po else 'sql_query'

            return intent if intent in ['document_generation', 'sql_query', 'chit_chat', 'clarification', 'follow_up_response', 'visualization', 'chart_selection'] else 'sql_query'
            
        except Exception as e:
            logger.error(f"Intent detection failed: {e}")
            return 'sql_query'  # Default to SQL query
        
    # ==================== DOCUMENT DETECTION ====================

    async def detect_document_type_and_requirements(
        self, user_query: str, context:str
    ) -> Dict[str, Any]:
        """Dynamically detect document type and missing requirements"""
        # context = ""
        # if conversation_history:
        #     # recent = [msg['content'][:50] for msg in conversation_history[-3:]]
        #     context = self._build_conversation_context(conversation_history[-3:])

        prompt = f"""You are an expert at understanding supply chain document generation requests.

        Analyze the user query along with previous conversation and determine document requirements:

        User Query: "{user_query}"
        Conversation Context: {context}
 
        Document types in supply chain:
        - purchase_order (PO)
        - invoice
        - shipping_note
        - inventory_report
        - demand_forecast_report
        - supplier_performance_report
        - quality_certificate
        - bill_of_materials (BOM)
        - delivery_challan


        Return JSON:
        {{
            "is_document_request": true/false,
            "document_type": "type_name or null",
            "confidence": 0.0-1.0,
            "missing_parameters": ["param1", "param2"],
            "extracted_parameters": {{"param": "value"}},
            "can_generate_immediately": true/false,
            "suggested_next_questions": ["question1?", "question2?"]
        }}
        """

        try:
            response = await self.client.chat.completions.create(
                model=self.NLP_LLM_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )

            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Document detection failed: {e}")
            return {
                "is_document_request": False,
                "confidence": 0.0
            }

    # ==================== CONTEXT-AWARE NEXT QUESTION SUGGESTION ====================
    async def suggest_next_questions(
        self,
        user_query: str,
        final_answer: str,
        intent: Optional[str] = None,
        query_results: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Suggest context-aware follow-up questions or next steps like any Chat assitant.
        Adapts based on intent and query result patterns (e.g., shortages, supplier issues).
        """

        # Lightweight heuristic before LLM call (avoids unnecessary token usage)
        suggestions = []

        # --- Ask the LLM ---
        if not suggestions:
            prompt = f"""
            You are a helpful assistant for supply chain management.
            The user asked: "{user_query}"
            You replied: "{final_answer}"
            Intent detected: {intent or "unknown"}

            Suggest 2–3 natural follow-up questions or next steps the user might take next,
            relevant to their intent or context. 
            - Be conversational
            - Be informative
            - Be creative to generate more natural language formal questions for business stakeholders
            - Suggest questions based on the current available services - document generation, quering results from database using SQL queries, or analysing data using relevant chart (currently addressing basic chart types)

            Examples:
            - User-> show me material with shortfall System->"I notice shortfalls. Would you like me to generate Purchase order for these items?
            - Asking for vendor details - "Do you want to see vendor details?"
            - "Should I forecast next week’s demand?"
            - "Do you want to analyse trend using line graph?"

            Respond in JSON only:
            {{
                "suggested_next_questions": ["question1", "question2", "question3"] (list of natural language questions suggested)
            }}
            """

            try:
                response = await self.client.chat.completions.create(
                    model=self.NLP_LLM_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.3
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                logger.error(f"LLM next-question suggestion failed: {e}")
                return {"suggested_next_questions": []}

        return {"suggested_next_questions": suggestions[:3]}
    
    # ==================== HANDLE FOLLOW-UP CONFIRMATION ====================
    async def handle_follow_up_confirmation(
        self,
        user_query: str,
        conversation_history: List[Dict],
        user_id: int,
        project_id: str
    ) -> Dict[str, Any]:
        """
        Handle confirmations like 'yes', 'okay', or modified follow-ups.
        Uses LLM to semantically interpret what the user wants next.
        """

        # positive_patterns = ["yes", "yeah", "sure", "please do", "go ahead", "ok", "okay", "yup"]
        # normalized = user_query.strip().lower()

        # Step 1: detect if it's a confirmation
        # if not any(p in normalized for p in positive_patterns):
        #     return {
        #         "intent": "follow_up_response",
        #         "final_answer": "I’m not sure what you mean — could you specify what you want me to do next?",
        #         "confidence": 0.5
        #     }

        # Step 1: find the last assistant message with next-question suggestions
        for msg in reversed(conversation_history):
            if msg["role"] == "assistant" and "suggested_next_questions" in msg.get("metadata", {}):
                suggestions = msg["metadata"]["suggested_next_questions"]
                if not suggestions:
                    continue

                # --- Step 2: use LLM to interpret user's confirmation or modification ---
                follow_up_prompt = f"""
                You are an intelligent assistant.
                The assistant previously suggested these follow-up actions:
                {json.dumps(suggestions, indent=2)}

                The user replied: "{user_query}"

                Task:
                - Determine if the user is confirming one of the suggestions, modifying it, or rejecting it.
                - If confirming or modifying, produce an actionable follow-up command.
                - If rejecting, respond politely with no action.

                Return JSON with this structure:
                {{
                "action_type": "confirm" | "modify" | "reject" | "unclear",
                "selected_suggestion": "<the matched suggestion text>",
                "action_query": "<the actionable query to execute>"
                }}
                """

                try:
                    response = await self.client.chat.completions.create(
                        model=self.NLP_LLM_model,
                        messages=[{"role": "user", "content": follow_up_prompt}],
                        response_format={"type": "json_object"},
                        temperature=0.2
                    )

                    result = json.loads(response.choices[0].message.content)
                    action_type = result.get("action_type", "")
                    action_query = result.get("action_query", "")
                    selected_action = result.get("selected_suggestion", "")

                    # --- Step 3: route behavior based on LLM output ---
                    if action_type in ["confirm", "modify"] and action_query:
                        logger.info(f"User confirmed/modifed follow-up: {action_query}")
                        result = await self.process_user_query(
                            action_query,
                            {},
                            user_id,
                            project_id
                        )

                        # Add metadata for storage
                        result["intent"] = "follow_up_response"
                        result["action_type"] = action_type
                        result["selected_suggestion"] = selected_action
                        result["action_query"] = action_query

                        return result
                    elif action_type == "reject":
                        return {
                            "intent": "follow_up_response",
                            "final_answer": "Got it — I won’t proceed with that action.",
                            "confidence": 0.9
                        }
                    else:
                        return {
                            "intent": "follow_up_response",
                            "final_answer": "I’m not completely sure what you mean — could you clarify?",
                            "confidence": 0.5
                        }

                except Exception as e:
                    logger.error(f"LLM follow-up confirmation failed: {e}")
                    break

        # Step 4: fallback if no matching assistant suggestion found
        return {
            "intent": "follow_up_response",
            "final_answer": "I’m not sure what you’re referring to — could you specify what I should do?",
            "confidence": 0.4
        }
    # ==================== SQL GENERATION & EXECUTION ====================
    async def generate_sql_response(
        self, 
        user_query: str, 
        relevant_data: Dict[str, Any],
        conversation_history: List[Dict],
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """Generate SQL query and natural language response"""
        
        # Build context from retrieved schemas
        if "error" in relevant_data and relevant_data.get("total_results", 0) == 0:
            return {
                "intent": "no_data",
                "explanation": "I couldn't find relevant information in your database to answer this query.",
                "final_answer": "I don't have enough information about your database schema to answer this question. Could you provide more details or try a different query?",
                "confidence": 0.1
            }
            
        # Build enhanced context from all sources
        db_context, business_context, reference_context = self._build_enhanced_context(relevant_data)

        # Enhanced conversation context - include SQL queries and results
        conversation_context = self._build_conversation_context(conversation_history)
        
        # Track retry attempts and errors
        sql_errors = []
        
        for attempt in range(max_retries + 1):
            try:
                # Build error context from previous attempts
                error_context = ""
                if sql_errors:
                    error_context = f"""
                                        PREVIOUS SQL ERRORS TO LEARN FROM:
                                        {chr(10).join([f"Attempt {i+1}: Error: {err['error']}" for i, err in enumerate(sql_errors)])}

                                        IMPORTANT: Fix these issues in your new SQL query:
                                        - Check column names exist in schema
                                        - Verify table names are correct
                                        - Fix JOIN syntax if needed
                                        - Handle DISTINCT/ORDER BY rules properly
                                        - Ensure no duplicate rows are created
                                        """
                system_prompt = f"""You are an expert SQL analyst and data consultant. Generate ONLY valid PostgreSQL queries using the provided schema information.
                    
                    {error_context}

                    1. Understand user intent from their natural language query
                    2. Generate SQL queries when appropriate using the provided database schema
                    3. Provide comprehensive explanations of your analysis
                    4. **Consider reference documentation for business policies, rules, and context**

                    CRITICAL RULES:
                    1. USE ONLY EXACT COLUMN NAMES from the schema - never assume or invent column names
                    2. USE ONLY EXACT TABLE NAMES from the schema
                    3. FOLLOW FOREIGN KEY RELATIONSHIPS exactly as specified in the schema
                    4. GENERATE CLEAN SQL ONLY - no assumptions, notes, or comments in the SQL query
                    5. PREVENT DUPLICATE ROWS - always consider using DISTINCT when joining tables
                    6. VALIDATE TABLE JOINS using the relationship information provided
                    7. USE PROPER AGGREGATION - when using subqueries, ensure they don't create duplicates
                    8. **APPLY BUSINESS POLICIES from reference documentation when relevant to the query**

                    ANTI-DUPLICATION GUIDELINES:
                    - Use DISTINCT when selecting from joined tables that might have one-to-many relationships
                    - In subqueries with JSON aggregation, ensure proper grouping to prevent duplicates
                    - Consider using EXISTS instead of JOIN when checking for relationships
                    - Use proper WHERE clauses to constrain results
                    - When using MIN/MAX in subqueries, be aware that multiple records might have the same min/max value

                    POSTGRESQL DISTINCT/ORDER BY RULES:
                    - When using SELECT DISTINCT, ORDER BY expressions MUST appear in the SELECT list
                    - Use DISTINCT ON (column) for PostgreSQL-specific distinct behavior
                    - Alternative: Use GROUP BY instead of DISTINCT when possible
                    - If ORDER BY column isn't in SELECT, either add it to SELECT or remove ORDER BY
                    - Example: SELECT DISTINCT col1, col2 FROM table ORDER BY col1, col2 - (RIGHT)
                    - Example: SELECT DISTINCT col1 FROM table ORDER BY col2 - (WRONG)

                    BETTER SQL PATTERNS:
                    - Instead of: SELECT DISTINCT column1 FROM table ORDER BY column2
                    - Use: SELECT DISTINCT column1, column2 FROM table ORDER BY column2
                    - Or use: SELECT DISTINCT ON (column1) column1, column2 FROM table ORDER BY column1, column2
                    - Or use: SELECT column1 FROM table GROUP BY column1 ORDER BY column1

                    Available Database Schemas:
                    {db_context}
                    
                    Conversation History:
                    {conversation_context}
                    
                    Available Business Logic Context:
                    {business_context}

                    Available Reference Documentation Context:
                    {reference_context}

                    Instructions:
                    - Use the database schema information to generate accurate SQL queries
                    - Only use tables and columns explicitly mentioned in the schema information
                    - Always use proper SQL syntax for PostgreSQL
                    - If you generate SQL, explain what the query does and why
                    - Consider previous conversation context for follow-up questions
                    - If you cannot generate SQL due to missing information, explain specifically what you need
                    - **Always look for reference documentation for any additional policies, constraints, or rules**

                    SQL query related Rules: 
                    - Use proper JOINs based on foreign key relationships shown in schema
                    - Include all relevant columns mentioned in the question
                    - Format with table.column references
                    - For location queries: Delhi → WHERE LOCATION_ID = 'IN01'
                    - Use ILIKE with % wildcards for case-insensitive text matching
                    - Use exact column names as shown in schema
                    - Follow the grain and primary key constraints
                    - Don't select table name in quotes
                    - Check for filter or constrain results based on policies mentioned in reference documentation
                    - Consider business rules when filtering or grouping data

                    Response Format:
                    Return a JSON object with these fields:
                    - "intent": "Brief description of query purpose"
                    - "sql_query": "CLEAN SQL QUERY WITHOUT COMMENTS OR NOTES"
                    - "explanation": "Natural language explanation"
                    - "tables_used": ["table1", "table2"] (list of tables used in SQL)
                    - "columns_referenced": ["table1.col1", "table2.col2"],
                    - "business_rules_applied": ["rule1", "rule2"] (business rules considered from given business context)
                    - "reference_context": ["ref1", "ref2"] (reference context used)
                    - "confidence": 0.0-1.0 (confidence in the response)

                    User Query: {user_query}"""
                    
                # Generate SQL with explanation using OpenAI
                response = await self.client.chat.completions.create(
                    model=self.LLM_model,
                    messages=[{"role": "system", "content": system_prompt}],
                    # temperature=0.1,
                    response_format={"type": "json_object"}
                )
                
                result = json.loads(response.choices[0].message.content)
                

                if "sql_query" in result and result.get("sql_query"):
                    query_result = await self.execute_sql_query(result["sql_query"])
                    result["query_result"] = query_result
                    
                    # Generate final natural language response with results
                    if query_result.get("success"):
                        final_response = await self.generate_final_response(
                            user_query, 
                            result["sql_query"], 
                            query_result["data"],
                            result["explanation"],
                            relevant_data
                        )
                        result["final_answer"] = final_response

                        if result.get("final_answer"):
                            next_suggestions = await self.suggest_next_questions(
                                user_query,
                                result["final_answer"],
                                intent=result.get("intent"),
                                query_results=result.get("query_result",{}).get("data",[])
                            )
                            if next_suggestions.get("suggested_next_questions"):
                                result["suggested_next_questions"] = next_suggestions["suggested_next_questions"]
                        logger.info(f"SQL query succeeded on attempt {attempt + 1}/{max_retries + 1}")
                        break
                    else:
                        # Log SQL error and prepare for retry
                        error_msg = query_result.get("error", "Unknown SQL error")
                        sql_errors.append({
                            "query": result["sql_query"][:100] + "...",
                            "error": error_msg,
                            "attempt": attempt + 1
                        })
                        
                        logger.warning(f"SQL attempt {attempt + 1} failed: {error_msg}")
                        
                        # If this was the last attempt, return error
                        if attempt == max_retries:
                            result["finalanswer"] = f"I tried {max_retries + 1} times but couldn't generate a working SQL query. Last error: {error_msg}"
                            result["sql_errors"] = sql_errors
                            result["confidence"] = 0.2
                        
                        # Continue to next retry (don't break)
                else:
                    # No SQL query generated
                    result["finalanswer"] = result.get("explanation", "No query generated")
                    break

            except Exception as e:
                logger.error(f"Error on SQL generation attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    return {
                        "intent": "error",
                        "explanation": f"Error after {max_retries + 1} attempts: {str(e)}",
                        "finalanswer": "I encountered errors while processing your request.",
                        "confidence": 0.0,
                        "sql_errors": sql_errors
                    }
        return result   
    
    async def execute_sql_query(self, sql_query: str) -> Dict[str, Any]:
        """Safely execute SQL query"""
        if not db.pool:
            return {"success": False, "error": "Database not available"}
        
        # Basic SQL injection protection - only allow SELECT statements
        sql_upper = sql_query.strip().upper()
        
        # Prevent dangerous operations
        dangerous_keywords = [
            'DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 
            'TRUNCATE', 'EXEC', 'EXECUTE', '--', '/*', '*/'
        ]
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                return {"success": False, "error": f"Query contains forbidden keyword: {keyword}"}
        try:
            async with db.pool.acquire() as connection:
                rows = await connection.fetch(sql_query)
                
                # Convert rows to list of dictionaries
                data = [dict(row) for row in rows]
                
                return {
                    "success": True,
                    "data": data,
                    "row_count": len(data)
                }
        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return {"success": False, "error": str(e)}
    
    async def generate_final_response(
        self, 
        user_query: str, 
        sql_query: str, 
        query_results: List[Dict], 
        explanation: str,
        relevant_data: Dict[str, Any]
    ) -> str:
        """Generate natural language response from SQL results"""

        # Handle empty results
        if not query_results:
            return f"No results found for your query. {explanation}"
        # Include context about business rules if they were used
        business_context = ""
        reference_context = ""

        if relevant_data.get('business_logic'):
            business_context = f"\n\nBased on your business rules: {relevant_data['business_logic'][0]['content'][:200]}..." if relevant_data['business_logic'] else ""
        
        if relevant_data.get('references'):
            reference_context = f"\n\nReferences: {', '.join(ref['content'] for ref in relevant_data['references'])}..." if relevant_data['references'] else ""
        
        prompt = f"""You are a helpful assistant.

            The user asked: {user_query}
            SQL Query Executed:{sql_query}
            SQL Query Results: {json.dumps(query_results, indent=2, default=str)}
            The SQL query returned: {len(query_results)} rows
            Reference Context: {reference_context}

            Instructions:
            - Provide a clear, conversational summary of the results
            - Focus on answering the user's specific question
            - Highlight key insights or patterns if relevant
            - Use business-friendly language
            - Be concise but informative
            - If there are many results, summarize the key findings
            - Include relevant business context when available
            - Include references to any relevant documents or data sources
            - Don't be overly formal or robotic
            Generate a professional, insightful response for a business stakeholder."""

        try:
            response = await self.client.chat.completions.create(
                model=self.NLP_LLM_model,
                messages=[
                            {"role": "system", "content": "You are an assistant that summarizes SQL query results into plain English."},
                            {"role": "user", "content": prompt}
                        ],
                temperature=0.1,
                max_tokens=300
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Based on the query results, I found {len(query_results)} records. {explanation}"
        
    async def get_or_create_conversation(self, user_id: int, project_id: str, user_query: str) -> str:
        """Get the latest conversation or create a new one"""
        try:
            # Get latest conversation for this project
            conversations = await db.get_user_conversations(user_id, project_id)
            
            if conversations:
                # Use the most recent conversation
                return conversations[0]['id']
            else:
                # Create new conversation with title from first query
                title = user_query[:50] + "..." if len(user_query) > 50 else user_query
                conversation = await db.create_conversation(user_id, project_id, title)
                return conversation['id']
        except Exception as e:
            logger.error(f"Error managing conversation: {e}")
            # Fallback to UUID
            return str(uuid.uuid4())

    async def store_conversation(self, conversation_id: str, user_id: int, project_id: str, query: str, response: Dict):
        """Store conversation in database"""
        try:
            # Store user message
            await db.store_chat_message(
                conversation_id=conversation_id,
                user_id=user_id,
                project_id=project_id,
                role='user',
                content=query
            )
            metadata = {}

            # Store base metadata if present
            if response.get("metadata"):
                metadata.update(response["metadata"])
            
            # Store chart object 
            if response.get("chart"):
                metadata["chart"] = response["chart"]
            
            # Store follow-up suggestion
            if response.get("followup_suggestions"):
                metadata["followup_suggestions"] = response["followup_suggestions"]

            if response.get("suggested_next_questions"):
                metadata["suggested_next_questions"] = response["suggested_next_questions"]
            
            # Store visualization suggestions
            if response.get("chart_suggestions"):
                metadata["chart_suggestions"] = response["chart_suggestions"]
            
            # Store data insights
            if response.get("data_insights"):
                metadata["data_insights"] = response["data_insights"]

            if response.get("requires_chart_selection"):
                metadata["requires_chart_selection"] = True

            # Store follow-up execution info (if from handle_follow_up_confirmation)
            if response.get("action_type"):
                metadata["follow_up_action"] = {
                    "action_type": response["action_type"],
                    "selected_suggestion": response.get("selected_suggestion"),
                    "executed_query": response.get("action_query"),
                }

            # if response.get("metadata") and isinstance(response["metadata"], dict):
            #     # The visualization handler already provides this structure
            #     metadata = response["metadata"]
                
            # Store assistant response
            await db.store_chat_message(
                conversation_id=conversation_id,
                user_id=user_id,
                project_id=project_id,
                role='assistant',
                content=response.get("final_answer", response.get("explanation", "")),
                sql_query=response.get("sql_query"),
                query_result=response.get("query_result"),
                intent=response.get("intent"),
                metadata=metadata,
                tables_used=response.get("tables_used", [])
            )
        except Exception as e:
            logger.error(f"Error storing conversation: {e}")

    async def get_conversation_history(self, conversation_id: str, user_id: int, for_llm: bool = True) -> List[Dict]:
        """Get conversation history from database"""
        try:
            messages = await db.get_conversation_messages(conversation_id, user_id)
            
            # Convert to format expected by the chat
            conversation_history = []
            for msg in messages:
                meta = msg.get('metadata')
            
                # Ensure metadata is a dict
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except json.JSONDecodeError:
                        meta = {}  # fallback for malformed JSON
                elif meta is None:
                    meta = {}
            
                # Filter metadata inline based on use case
                if for_llm and meta:
                    # Create filtered copy for LLM
                    filtered_meta = {}
                    
                    if 'suggested_next_questions' in meta and meta['suggested_next_questions']:
                        filtered_meta['suggested_next_questions'] = meta['suggested_next_questions']
                    
                    # Keep chart TYPE only, strip heavy data
                    if 'chart' in meta and isinstance(meta['chart'], dict):
                        filtered_meta['chart'] = {
                            'chart_type': meta['chart'].get('chart_type'),
                            'title': meta['chart'].get('title'),
                            'data_points': meta['chart'].get('data_points'),
                        }
                    
                    # Keep followup text only
                    if 'followup_suggestions' in meta and isinstance(meta['followup_suggestions'], list):
                        filtered_meta['followup_suggestions'] = [
                            s.get('text') if isinstance(s, dict) else s 
                            for s in meta['followup_suggestions'][:5]
                        ]
                    
                    # Keep chart suggestion types only
                    if 'chart_suggestions' in meta and isinstance(meta['chart_suggestions'], list):
                        filtered_meta['chart_suggestions'] = [
                            {
                                'chart_type': s.get('chart_type'),
                                'reason': s.get('reason', '')[:200]
                            }
                            for s in meta['chart_suggestions'][:3]
                        ]
                    
                    if '_pending_viz_data' in meta and isinstance(meta['_pending_viz_data'], dict):
                        filtered_meta['_pending_viz_data'] = meta['_pending_viz_data']
                    
                    # # Keep data insights summary only
                    # if 'data_insights' in meta:
                    #     insights = meta['data_insights']
                    #     if isinstance(insights, dict):
                    #         filtered_meta['data_insights'] = {
                    #             'row_count': insights.get('row_count'),
                    #             'column_count': insights.get('column_count'),
                    #         }
                    
                    # Keep follow-up action summary
                    if 'follow_up_action' in meta and isinstance(meta['follow_up_action'], dict):
                        filtered_meta['follow_up_action'] = meta['follow_up_action']
                    
                    meta = filtered_meta
                conversation_history.append({
                    'role': msg['role'],
                    'content': msg['content'],
                    'sql_query': msg.get('sql_query'),
                    'intent': msg.get('intent'),
                    'metadata': meta,
                    'timestamp': msg['created_at']
                })
            
            return conversation_history
        except Exception as e:
            logger.error(f"Error fetching conversation history: {e}")
            return []

    # async def _llm_verify_po_intent(self, user_query: str) -> bool:
    #     """Use LLM to verify if query is really about Document generation"""
    #     try:
    #         prompt = f"""
    #             Analyze this user query and determine if the user wants to generate/create a document.

    #             Query: "{user_query}"

    #             Respond with only "YES" if the query is asking to:
    #             - Generate, create, or make a purchase order
    #             - Create a PO for a specific date
    #             - Generate procurement documents
    #             - Order materials due to shortfall

    #             Respond with only "NO" if the query is asking about:
    #             - Viewing existing POs
    #             - Analyzing data
    #             - General questions
    #             - Other operations

    #             Response:"""

    #         response = await self.client.chat.completions.create(
    #             model=self.NLP_LLM_model,
    #             messages=[{"role": "user", "content": prompt}],
    #             max_tokens=5,
    #             temperature=0.1
    #         )
            
    #         result = response.choices[0].message.content.strip().upper()
    #         return result == "YES"
            
    #     except Exception as e:
    #         logger.warning(f"LLM verification failed: {e}")
    #         return True  # Default to True if LLM fails
        
    async def extract_date_from_query_llm(self, user_query: str, context:str) -> str:
        """Extract date from query using LLM - much more flexible"""
        
        try:
            current_date = datetime.now().strftime("%m/%d/%Y")  # e.g., 09/22/2025
            
            prompt = f"""Extract the date from this user query about document generation. 
                Your task is to identify which date the user intends for this PO generation request.

                Use these rules carefully:

                1. First, look for **explicit dates or date phrases** in the current query.
                - Examples: "today", "tomorrow", "10/10", "Oct 10", "next Monday", "this Friday".
                - If found → use that and ignore previous conversation context.
                - If user says "today" or "now" → return "today"
                - If user says "tomorrow" → return "tomorrow" 
                - If user says "yesterday" → return "yesterday"
                - If user mentions specific dates like "sep 22nd", "22/09", "September 22" → return the exact text
                - If user says "next monday", "this friday" → return the exact text
                - If no date is mentioned → return "today"

                2. If **no date mentioned in current query**, then:
                - Check previous conversation context to see if the user recently referred to a date
                    (e.g., “show shortfall for 10/10”, “analyze order for next week”).
                - If a recent date reference exists, reuse that same date.
                - But only reuse if the conversation context is clearly related (like follow-up queries).

                3. If neither current query nor recent context mentions a date, use **today** as the default.

                4. Do NOT use old or unrelated conversation dates if they appear outdated or not relevant to current intent.

                Conversation context (for reference):
                {context}

                Today's date: {current_date}

                User query: "{user_query}"

                Extract only the date portion. Examples:
                - "generate PO for today" → "today"
                - "create purchase order for tomorrow" → "tomorrow"
                - "make PO for sep 22nd 2025" → "sep 22nd 2025"
                - "generate PO for next monday" → "next monday"
                - "create PO" → "today"

                If no date is specified consider it for today's date, also analyse the user query, if it's a new request for generating document and no date is mentioned, consider today's date.

                Response (only the date part):"""

            response = await self.client.chat.completions.create(
                model=self.NLP_LLM_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0.1
            )
            
            extracted_date = response.choices[0].message.content.strip().lower()
            
            # Clean up common LLM artifacts
            extracted_date = extracted_date.replace('"', '').replace("'", "").strip()
            
            # Default to today if extraction fails
            if not extracted_date or len(extracted_date) < 2:
                extracted_date = "today"
                
            logger.info(f"📅 LLM extracted date: '{user_query}' → '{extracted_date}'")
            return extracted_date
            
        except Exception as e:
            logger.error(f"LLM date extraction failed: {e}")
            return "today"  # Safe fallback

    # ==================== DOCUMENT GENERATION HANDLERS ====================

    async def handle_document_generation(
        self, user_query: str, user_id: int, project_id: str, conversation_history: List[Dict]
    ) -> Dict[str, Any]:
        """Handle document generation requests"""
        context = ""
        if conversation_history:
            # recent = [msg['content'][:50] for msg in conversation_history[-3:]]
            context = self._build_conversation_context(conversation_history[-4:])

        # Detect document type and requirements
        doc_detection = await self.detect_document_type_and_requirements(
            user_query, context
        )

        if not doc_detection.get("is_document_request") or doc_detection.get("confidence", 0) < 0.7:
            return {
                "intent": "clarification_needed",
                "final_answer": "I'm not sure what document you want to generate. Could you please specify? (e.g., purchase order, invoice, report)",
                "confidence": 0.5
            }

        doc_type = doc_detection.get("document_type")

        # Handle purchase order generation
        if doc_type == "purchase_order":
            # active_session = enhanced_intelligent_po_service_combined._get_user_active_session(
            #     user_id, project_id
            # )
            # if active_session:
                # User is responding to a confirmation step
                # Route directly to PO service (bypass intent detection)
                # result = await enhanced_intelligent_po_service_combined.start_po_workflow(
                #     user_id=user_id,
                #     project_id=project_id,
                #     user_query=user_query,
                #     conversation_history=conversation_history,
                #     order_date=None
                # )

                # return result
            
            return await self.handle_po_generation_request(user_query, user_id, project_id, conversation_history, context)

        # Handle other document types
        else:
            return {
                "intent": "document_generation",
                "final_answer": f"Document generation for {doc_type} is not yet implemented. Currently, I can generate purchase orders. Would you like me to generate a PO instead?",
                "confidence": 0.7,
                "document_type": doc_type
            }
        
    async def handle_po_generation_request(self, user_query: str, user_id: int, project_id: str, conversation_history: List[Dict], context:str) -> Dict[str, Any]:
        """Handle PO generation request - trigger workflow in background"""
        
        try:
            # Extract date from query
            extracted_date = await self.extract_date_from_query_llm(user_query, context)
            
            # Parse date
            # parsed_date, is_valid = parse_user_date_safe(extracted_date)

            parsed_date = await self.date_parser.parse_date_llm(extracted_date)

            # Trigger PO workflow in background using existing service
            logger.info(f"🤖 PO generation via chat: '{user_query}' -> '{extracted_date}' -> '{parsed_date}'")
            
            # result = await enhanced_intelligent_po_service_combined.start_po_workflow(
            #     user_id=user_id,
            #     project_id=project_id,
            #     order_date=parsed_date,
            #     user_query=user_query,
            #     conversation_history=conversation_history,
            # )
            result = await po_workflow_service.start_po_workflow(
                user_id=user_id,
                project_id=project_id,
                order_date=parsed_date,
                user_query=user_query,
                conversation_history=conversation_history,
            )
            # return result
            if result.get("success"):
                return {
                    "intent": "po_generation",
                    "explanation": f"Intelligent Document generation started for {parsed_date}",
                    "workflow_id": result.get("workflow_id"),
                    "final_answer": f"🤖 Document Generation Started\n\n"
                                  f"I'm analyzing your request for {result.get("user_query_scope", user_query)}...\n\n"
                                #   f"💡What I'm doing:\n"
                                #     f"- Understanding your specific requirements\n"
                                #     f"- Checking inventory and shortfalls\n"
                                #     f"- Finding optimal vendors\n"
                                #     f"- Generating purchase orders\n\n"
                                  f"Watch the sidebar for real-time progress!\n\n"
                                  f"💬 You can continue our conversation while I process this.",
                    "confidence": 0.95,
                    "tables_used": [],
                    "po_workflow_started": True,
                }
            else:
                return {
                    "intent": "po_generation_failed",
                    "explanation": f"Failed to start PO generation for {parsed_date}.",
                    "final_answer": f"❌ I couldn't start the PO generation for {parsed_date}. {result.get('message', 'Please try again or check the system status.')}",
                    "confidence": 0.8,
                    "tables_used": []
                }
                
        except Exception as e:
            logger.error(f"Error handling PO generation request: {e}")
            return {
                "intent": "po_generation_error",
                "explanation": f"System error during PO generation.",
                "final_answer": f"❌ I encountered an error while trying to generate the purchase order. Please try again.",
                "confidence": 0.5,
                "tables_used": []
            }

    # Handle Chit-Chat
    async def generate_chit_chat_response(self, user_query: str, conversation_history: List[Dict]) -> str:
        """Generate friendly conversational responses"""
        
        # Pattern-based responses for common cases
        query_lower = user_query.lower().strip()
        
        if any(greet in query_lower for greet in ['hi', 'hello', 'hey']):
            return "Hello! I'm your Supply Chain Assistant. I can help you query your database and analyze your data. What would you like to know?"
        
        if any(thanks in query_lower for thanks in ['thank', 'thanks']):
            return "You're welcome! Feel free to ask me anything about your data."
        
        if any(bye in query_lower for bye in ['bye', 'goodbye']):
            return "Goodbye! Come back anytime you need help with your data."

        # Use LLM for more complex conversations
        context = ""
        if conversation_history:
            recent_context = []
            for msg in conversation_history[-4:]:
                role = "User" if msg['role'] == 'user' else "Assistant"
                recent_context.append(f"{role}: {msg['content']}")
            context = "\n".join(recent_context)

        prompt = f"""You are a helpful and friendly Supply Chain SQL Assistant for a business intelligence platform.

            {f"Recent conversation context: {context}" if context else ""}

            User says: "{user_query}"

            Respond in a conversational, helpful manner. Keep responses short and friendly. If appropriate, mention that you can help with database queries and data analysis.

            Guidelines:
            - Be warm and professional
            - Keep responses concise (1-2 sentences)
            - If relevant, mention your ability to help with data queries
            - Don't be overly formal or robotic"""

        try:
            response = await self.client.chat.completions.create(
                model=self.NLP_LLM_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=100
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Chit-chat generation failed: {e}")
            return "I'm here to help you with your data queries. What would you like to know?"

    # NEW: Handle Clarification Requests
    async def generate_clarification_response(self, user_query: str, conversation_history: List[Dict]) -> str:
        """Handle questions about capabilities and help requests"""
        
        help_response = """I'm your Supply Chain Assistant! Here's what I can help you with:

            🔍 Data Queries: Ask questions about your data in natural language
            - "Show me sales for last quarter"
            - "How many customers do we have?"
            - "What's the average order value?"

            📊 Data Analysis: Get insights and summaries
            - "Which products are performing best?"
            - "Show me trends in customer behavior"

            🛒 Purchase Order Generation: Create POs automatically
            - "generate PO for today"
            - "create purchase order for tomorrow"
            - "make PO for sep 22nd 2025"

            💬 Follow-up Questions: Build on previous queries
            - "Add a filter for region"
            - "Sort that by date"
            - "Show me more details"

            Just ask me anything about your data in plain English, and I'll run the analysis for you!"""

        query_lower = user_query.lower()
        if any(word in query_lower for word in ['help', 'what can you', 'how do i', 'what do you do']):
            return help_response
        
        return "I can help you query your database, analyze your data, and generate purchase orders.. Just ask me questions in natural language! For example: 'Show me sales data for last month' or 'How many customers do we have?'"
    
    async def handle_visualization_request(
        self,
        user_query: str,
        relevant_data: Dict[str, Any],
        conversation_history: List[Dict],
        user_id: int,
        project_id: str,
        conversation_id : str
    ) -> Dict[str, Any]:
        """Handle requests that need data visualization"""
        
        try:
            # First, get the data via SQL
            sql_result = await self.generate_sql_response(
                user_query, 
                relevant_data, 
                conversation_history
            )
            
            if not sql_result.get("query_result", {}).get("success"):
                return {
                    "intent": "visualization_failed",
                    "explanation": "I couldn't retrieve the data needed for visualization.",
                    "final_answer": sql_result.get("final_answer", "Unable to fetch data."),
                    "confidence": 0.5
                }
            
            data = sql_result["query_result"].get("data", [])
            
            if not data or len(data) == 0:
                return {
                    "intent": "visualization_no_data",
                    "explanation": "No data available to visualize.",
                    "final_answer": "I couldn't find any data to visualize for your query.",
                    "confidence": 0.6,
                    "sql_query": sql_result.get("sql_query")
                }
            # Keyword-based chart type detection 
            detected_chart_type = chart_service._detect_chart_type_by_keywords(user_query)
            
            # If user explicitly specified chart type with high confidence
            if detected_chart_type and detected_chart_type != "none":
                data_sample = data[0] if data else {}
                chart_title = await chart_service.generate_chart_title_by_llm(
                    user_query, detected_chart_type, data_sample
                )
                
                logger.info(f"⚡ Generating {detected_chart_type} chart with title: {chart_title}")
                # Generate chart directly
                chart_result = await chart_service.generate_chart(
                    data=data,
                    chart_type=detected_chart_type,
                    title=chart_title,
                    config=None,
                    original_query=user_query
                )
                
                if chart_result.get('success'):
                    try:
                        await db.store_chart_in_history(
                            chart_result, conversation_id, user_id, project_id
                        )
                    except Exception as e:
                        logger.warning(f"Failed to store chart: {e}")
                    
                    return {
                        "intent": "visualization_complete",
                        "explanation": sql_result.get("explanation", ""),
                        "final_answer": f"Here's your {detected_chart_type} chart:",
                        "sql_query": sql_result.get("sql_query"),
                        "query_result": sql_result.get("query_result"),
                        "chart": {
                            "success": chart_result['success'],
                            "chart_id": chart_result['chart_id'],
                            "chart_json": chart_result['chart_json'],
                            "chart_html": chart_result['chart_html'],
                            "chart_png_base64": chart_result.get('chart_png_base64'),
                            "chart_type": chart_result['chart_type'],
                            "title": chart_result['title'],
                            "data_points": chart_result['data_points'],
                            "columns_used": chart_result['columns_used'],
                            "timestamp": chart_result['timestamp'],
                            "followup_suggestions": chart_result.get('followup_suggestions', [])
                        },
                        "followup_suggestions": chart_result.get('followup_suggestions', []),
                        "metadata": {
                            "chart": chart_result,
                            "followup_suggestions": chart_result.get('followup_suggestions', []),
                            "is_direct_generation": True,
                            "_pending_viz_data": {
                                    'suggestions': {
                                        'success': True,
                                        'suggestions': [{
                                            'chart_type': detected_chart_type,
                                            'config': {},
                                            'title': chart_title,
                                        }]
                                    },
                                    'data': data,
                                    'original_query': user_query
                             }
                        },
                        "confidence": 0.95
                    }
            # llm_analysis = chart_service._detect_chart_type_by_LLM(user_query)
            # if llm_analysis and llm_analysis!="none":
            #     chart_type = llm_analysis.get("chart_type")
            #     confidence = llm_analysis.get("confidence", 0)
            #     chart_title = llm_analysis.get("chart_title","")
                
            #     logger.info(f"📊 LLM: chart_type={chart_type}, confidence={confidence}")
                
            #     # If LLM says no visualization, return SQL result
            #     if chart_type == "none" or confidence < 0.5:
            #         logger.info("📊 No visualization needed or low confidence")
            #         return sql_result
                
            #     # If high confidence, generate chart directly
            #     if confidence >= 0.7:
            #         logger.info(f"⚡ Generating {chart_type} directly (confidence: {confidence})")
                    
            #         chart_result = await chart_service.generate_chart(
            #             data=data,
            #             chart_type=chart_type,
            #             title=chart_title if chart_title!= "" else f"{chart_type.title()} Analysis",
            #             config=None,
            #             original_query=user_query
            #         )
                    
            #         if chart_result.get('success'):
            #             try:
            #                 await db.store_chart_in_history(
            #                     chart_result, conversation_id, user_id, project_id
            #                 )
            #             except Exception as e:
            #                 logger.warning(f"Failed to store chart: {e}")
                        
            #             return {
            #                 "intent": "visualization_complete",
            #                 "explanation": sql_result.get("explanation", ""),
            #                 "final_answer": f"Here's your {chart_type} chart:",
            #                 "sql_query": sql_result.get("sql_query"),
            #                 "query_result": sql_result.get("query_result"),
            #                 "chart": {
            #                     "success": chart_result['success'],
            #                     "chart_id": chart_result['chart_id'],
            #                     "chart_json": chart_result['chart_json'],
            #                     "chart_html": chart_result['chart_html'],
            #                     "chart_png_base64": chart_result.get('chart_png_base64'),
            #                     "chart_type": chart_result['chart_type'],
            #                     "title": chart_result['title'],
            #                     "data_points": chart_result['data_points'],
            #                     "columns_used": chart_result['columns_used'],
            #                     "timestamp": chart_result['timestamp'],
            #                     "followup_suggestions": chart_result.get('followup_suggestions', [])
            #                 },
            #                 "followup_suggestions": chart_result.get('followup_suggestions', []),
            #                 "metadata": {
            #                     "chart": chart_result,
            #                     "followup_suggestions": chart_result.get('followup_suggestions', [])
                                # "is_direct_generation": True,
                                #                 "_pending_viz_data": {
                                #                         'suggestions': {
                                #                             'success': True,
                                #                             'suggestions': [{
                                #                                 'chart_type': detected_chart_type,
                                #                                 'config': {},
                                #                                 'title': chart_title,
                                #                             }]
                                #                         },
                                #                         'data': data,
                                #                         'original_query': user_query
                                #                 }
            #                 },
            #                 "confidence": 0.95
            #             }

            
            # Low confidence or failed LLM - show suggestions
            logger.info("🎨 Showing chart suggestions")
            # Get AI chart suggestions with thumbnails
            suggestions_result = await chart_service.suggest_chart_options(
                query=user_query,
                data=data,
                intent="visualization"
            )
            
            if not suggestions_result.get('success'):
                return sql_result
            
            metadata_for_storage = {
            '_pending_viz_data': {
                'suggestions': suggestions_result,
                'data': data,
                'original_query': user_query
            },
            "is_direct_generation": False,
            'suggested_next_questions': suggestions_result.get('suggested_questions', []),
            'data_insights': suggestions_result.get('data_insights', '')
        }
            
            return {
                "intent": "visualization_pending",
                "explanation": sql_result.get("explanation", ""),
                "final_answer": f"I found {len(data)} data points. Please select your preferred visualization:",
                "sql_query": sql_result.get("sql_query"),
                "query_result": sql_result.get("query_result"),
                "chart_suggestions": suggestions_result['suggestions'],
                "data_insights": suggestions_result.get('data_insights', ''),
                "suggested_next_questions": suggestions_result.get('suggested_questions', []),
                "requires_chart_selection": True,
                "confidence": 0.9,
                "metadata": metadata_for_storage
            }
            
        except Exception as e:
            logger.error(f"Visualization error: {e}")
            return {"intent": "error", "final_answer": f"Error: {str(e)}"}


    async def handle_chart_selection(
        self,
        user_query: str,
        conversation_history: List[Dict],
        user_id: int,
        project_id: str,
        conversation_id: str
    ) -> Dict[str, Any]:
        """Handle user selecting a chart type from suggestions"""
        
        try:
            # Get pending visualization from conversation
            pending_viz = None
            for msg in reversed(conversation_history):
                if msg.get('role') == 'assistant' and msg.get('metadata'):
                    metadata = msg['metadata']
                    # Parse metadata if it's a string
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except:
                            continue
                    
                    # Check if this message has pending visualization data
                    if '_pending_viz_data' in metadata:
                        pending_viz = metadata['_pending_viz_data']
                        break
            
            if not pending_viz:
                return {
                    "intent": "error",
                    "final_answer": "No pending visualization found. Please ask for a visualization first."
                }
            
            # suggestions = json.loads(pending_viz['suggestions'])
            # data = json.loads(pending_viz['data'])
            # original_query = pending_viz.get('original_query', user_query)
            suggestions = pending_viz.get('suggestions', {})
            if isinstance(suggestions, str):
                try:
                    suggestions = json.loads(suggestions)
                except:
                    logger.error("Failed to parse suggestions")
                    return {"intent": "error", "final_answer": "Error parsing chart suggestions."}
            
            data = pending_viz.get('data', [])
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except:
                    logger.error("Failed to parse data")
                    return {"intent": "error", "final_answer": "Error parsing visualization data."}
            
            original_query = pending_viz.get('original_query', user_query)
            
            # Determine which chart user selected
            selection_prompt = f"""
                                User was shown these chart options:
                                {json.dumps([s['chart_type'] for s in suggestions['suggestions']], indent=2)}

                                User's response: {user_query}

                                Determine which chart type the user selected or want. Respond with JSON:
                                {{
                                "selected_chart_type": "chart_type_name",
                                "confidence": 0.95
                                }}
                            """
            
            response = await self.client.chat.completions.create(
                model=self.NLP_LLM_model,
                messages=[{"role": "user", "content": selection_prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            selection = json.loads(response.choices[0].message.content)
            selected_type = selection['selected_chart_type']
            
            # Find the config for selected chart
            config = None
            title = "Data Visualization"
            for sug in suggestions['suggestions']:
                if sug['chart_type'] == selected_type:
                    config = sug.get('config')
                    title = sug.get('title', title)
                    break
            
            # Generate the chart
            logger.info(f"Generating {selected_type} chart with {len(data)} data points")
            chart_result = await chart_service.generate_chart(
                data=data,
                chart_type=selected_type,
                title=title,
                config=config,
                original_query=original_query
            )
            if not chart_result.get('success'):
                logger.error(f"Chart generation failed: {chart_result.get('error')}")
                return {
                    "intent": "error",
                    "final_answer": f"Failed to generate chart: {chart_result.get('error', 'Unknown error')}"
                }
            if chart_result.get('success'):
                # Store chart in history
                await db.store_chart_in_history(
                    chart_result,
                    conversation_id,
                    user_id,
                    project_id
                )
            
                # # Clear pending visualization
                # await db.execute(
                #     """
                #     UPDATE chat_messages 
                #     SET metadata = metadata - 'pending_visualization' - 'visualization_data' - 'original_query'
                #     WHERE conversation_id = $1
                #     """,
                #     conversation_id
                # )
            
            return {
                "intent": "visualization_complete",
                "final_answer": f"Here's your {selected_type} chart:",
                "chart": {
                "success": chart_result['success'],
                "chart_id": chart_result['chart_id'],
                "chart_json": chart_result['chart_json'],
                "chart_html": chart_result['chart_html'],
                "chart_png_base64": chart_result.get('chart_png_base64'),
                "chart_type": chart_result['chart_type'],
                "title": chart_result['title'],
                "data_points": chart_result['data_points'],
                "columns_used": chart_result['columns_used'],
                "timestamp": chart_result['timestamp'],
                "followup_suggestions": chart_result.get('followup_suggestions', [])
                    },
                "followup_suggestions": chart_result.get('followup_suggestions', []),
                "metadata": {
                    "chart": {
                        "success": chart_result['success'],
                        "chart_id": chart_result['chart_id'],
                        "chart_json": chart_result['chart_json'],
                        "chart_html": chart_result['chart_html'],
                        "chart_png_base64": chart_result.get('chart_png_base64'),
                        "chart_type": chart_result['chart_type'],
                        "title": chart_result['title'],
                        "data_points": chart_result['data_points'],
                        "columns_used": chart_result['columns_used'],
                        "timestamp": chart_result['timestamp']
                    },
                    "followup_suggestions": chart_result.get('followup_suggestions', [])
                },
                "confidence": 0.95
            }
            
        except Exception as e:
            logger.error(f"Chart selection error: {e}")
            return {"intent": "error", "final_answer": f"Error: {str(e)}"}

    # Main Query Processing
    async def process_user_query(
        self,
        user_query: str,
        relevant_data: Dict[str, Any],
        user_id: int,
        project_id: str
    ) -> Dict[str, Any]:
        """Main entry point that handles all types of queries"""
        
        try:
             # Get or create conversation
            conversation_id = await self.get_or_create_conversation(user_id, project_id, user_query)
            
            # Get conversation history for context (last 10 messages)
            conversation_history = await self.get_conversation_history(conversation_id, user_id)
            conversation_history = conversation_history[-10:]  # Keep last 10 for context

            # Detect intent
            intent = await self.detect_query_intent(user_query, conversation_history)
            logger.info(f"Detected intent: {intent} for query: '{user_query}'")

            # Step 2: Route based on intent
            if intent == 'document_generation':
                result = await self.handle_document_generation(
                    user_query, user_id, project_id, conversation_history
                )
                
            elif intent == 'follow_up_response':
                result = await self.handle_follow_up_confirmation(
                    user_query, conversation_history, user_id, project_id
                )

            elif intent == 'chit_chat':
                response_text = await self.generate_chit_chat_response(user_query, conversation_history)
                result = {
                    "intent": "chit_chat",
                    "explanation": response_text,
                    "final_answer": response_text,
                    "confidence": 0.95,
                    "tables_used": []
                }
                
            elif intent == 'clarification':
                response_text = await self.generate_clarification_response(user_query, conversation_history)
                result = {
                    "intent": "clarification",
                    "explanation": response_text,
                    "final_answer": response_text,
                    "confidence": 0.9,
                    "tables_used": []
                }

            elif intent == "chart_selection":
                result = await self.handle_chart_selection(user_query, conversation_history, user_id, project_id, conversation_id)
            
            elif intent == "visualization":
                result = await self.handle_visualization_request(
                    user_query, 
                    relevant_data, 
                    conversation_history,
                    user_id,
                    project_id,
                    conversation_id
                )
                
            else:  # sql_query intent
                # SQL generation flow
                result = await self.generate_sql_response(
                    user_query,
                    relevant_data,
                    conversation_history
                )
            
            if result.get("query_result") and result["query_result"].get("success"):
                data = result["query_result"]["data"]
                row_count = len(data)
                # if self._check_shortfall_in_data(data):
                #     result["po_suggestion"] = {
                #         "suggest_po": True,
                #         "reason": "Query results indicate material shortfall",
                #         "suggestion_text": "💡 I notice this data shows material shortfalls. Would you like me to generate purchase orders to address these shortages? Just say 'generate PO for today' or specify a date."
                #     }
                #     result["final_answer"] += "\n\n" + result["po_suggestion"]["suggestion_text"]

                # Store nested
                if row_count > 10:
                    result["query_result"]["sample_data"] = data[:10]
                else:
                    result["query_result"]["sample_data"] = data
                result["query_result"]["row_count"] = row_count
                
                # Also store at top level for easy access
                result["sample_data"] = result["query_result"]["sample_data"]
                result["total_rows"] = row_count

            # Step 3: Store conversation
            await self.store_conversation(conversation_id, user_id, project_id, user_query, result)
            
            # Add conversation_id to result
            result['conversation_id'] = conversation_id
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing user query: {e}")
            return {
                "intent": "error",
                "explanation": f"I encountered an error: {str(e)}",
                "final_answer": "I'm sorry, I encountered an error. Please try again.",
                "confidence": 0.0
            }

# Global instance
rag_sql_service = SQLRAGService()
