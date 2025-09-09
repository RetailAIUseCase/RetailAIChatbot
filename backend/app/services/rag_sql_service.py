"""
RAG SQL Service for natural language to SQL conversion
"""
import asyncio
import json
import re
from typing import Dict, List, Any, Optional, Tuple
import uuid
from openai import AsyncOpenAI
from app.database.connection import db
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

class SQLRAGService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        # self.conversation_memory = {}  # Store conversation history
        self.Embedding_model = settings.EMBED_MODEL
        self.LLM_model = settings.LLM_MODEL
        self.NLP_LLM_model = settings.NLP_LLM_MODEL
        self.embedding_dimensions = settings.EMBEDDING_DIMENSIONS

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
                    connection, query_embedding, user_id, project_id, top_k//3, similarity_threshold
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

        # table_query = """
        # SELECT 
        #     table_name,
        #     content_type,
        #     content,
        #     metadata,
        #     (embedding <=> $1) as distance,
        #     (1 - (embedding <=> $1)) as similarity
        # FROM metadata_embeddings 
        # WHERE user_id = $2 AND project_id = $3 AND content_type = 'table'
        #     AND (1 - (embedding <=> $1)) >= 0.2  -- Similarity threshold
        # ORDER BY embedding <=> $1
        # LIMIT $4
        # """
        
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
                    db_context += f"**Schema** (relevance: {table_info['similarity']:.2f}):\n{table_info['content']}\n\n"
                
                # Clean column information
                for col_info in tables_info[table_name]['column']:
                    # clean_content = self._clean_column_content(col_info['content'])
                    db_context += f"**Columns** (relevance: {col_info['similarity']:.2f}):\n{col_info['content']}\n\n"
                
                # Clean relationship information
                for rel_info in tables_info[table_name]['relationship']:
                    # clean_content = self._clean_relationship_content(rel_info['content'])
                    db_context += f"**Relationships** (relevance: {rel_info['similarity']:.2f}):\n{rel_info['content']}\n\n"

        # Business logic context
        if retrieval.get('business_logic'):
            business_context += "\nBUSINESS RULES & LOGIC:\n"
            for rule in retrieval['business_logic'][:3]:  # Top 3 rules
                business_context += f"\n**Rule {rule['rule_number']}** (similarity: {rule['similarity']:.2f}):\n{rule['content']}\n"

        # Reference context
        if retrieval.get('references'):
            reference_context += "\nREFERENCE DOCUMENTATION:\n"
            for ref in retrieval['references'][:2]:  # Top 2 references
                reference_context += f"\n**Reference** (similarity: {ref['similarity']:.2f}):\n{ref['content'][:300]}...\n"
        
        return db_context, business_context, reference_context

    def _build_conversation_context(self, conversation_history: List[Dict]) -> str:
        """Build conversation context string"""
        context = ""
        if conversation_history:
            context = "**Previous Conversation Context:**\n"
            for msg in conversation_history:  # Last 6 messages
                if msg['role'] == 'user':
                    context += f"User: {msg['content']}\n"
                elif msg['role'] == 'assistant':
                    context += f"Assistant: {msg['content']}\n"
                    # Include the SQL query if available
                    if msg.get('sql_query'):
                        context += f"Previous SQL Query: {msg['sql_query']}\n"
                    # Include query intent
                    if msg.get('intent'):
                        context += f"Previous Intent: {msg['intent']}\n"
                context += "\n"
        return context

    async def generate_sql_response(
        self, 
        user_query: str, 
        relevant_data: Dict[str, Any],
        conversation_history: List[Dict],
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
        # print("DB CONTEXT", db_context)
        # print("BUSINESS CONTEXT", business_context)

        # Enhanced conversation context - include SQL queries and results
        conversation_context = self._build_conversation_context(conversation_history)
        
            
        system_prompt = f"""You are an expert SQL analyst and data consultant. Generate ONLY valid PostgreSQL queries using the provided schema information.

            1. **Understand user intent** from their natural language query
            2. **Generate SQL queries** when appropriate using the provided database schema
            3. **Provide comprehensive explanations** of your analysis

            **CRITICAL RULES:**
            1. **USE ONLY EXACT COLUMN NAMES** from the schema - never assume or invent column names
            2. **USE ONLY EXACT TABLE NAMES** from the schema
            3. **FOLLOW FOREIGN KEY RELATIONSHIPS** exactly as specified in the schema
            4. **GENERATE CLEAN SQL ONLY** - no assumptions, notes, or comments in the SQL query
            5. **PREVENT DUPLICATE ROWS** - always consider using DISTINCT when joining tables
            6. **VALIDATE TABLE JOINS** using the relationship information provided
            7. **USE PROPER AGGREGATION** - when using subqueries, ensure they don't create duplicates

            **ANTI-DUPLICATION GUIDELINES:**
            - Use DISTINCT when selecting from joined tables that might have one-to-many relationships
            - In subqueries with JSON aggregation, ensure proper grouping to prevent duplicates
            - Consider using EXISTS instead of JOIN when checking for relationships
            - Use proper WHERE clauses to constrain results
            - When using MIN/MAX in subqueries, be aware that multiple records might have the same min/max value

            **Available Database Schemas:**
            {db_context}

            **Reference Context:**
            {reference_context}

            **Conversation History:**
            {conversation_context}

            **Instructions:**
            - Use the database schema information to generate accurate SQL queries
            - Only use tables and columns explicitly mentioned in the schema information
            - Always use proper SQL syntax for PostgreSQL
            - If you generate SQL, explain what the query does and why
            - Consider previous conversation context for follow-up questions
            - If you cannot generate SQL due to missing information, explain specifically what you need

            ** SQL query related Rules: **
            - Use proper JOINs based on foreign key relationships shown in schema
            - Include all relevant columns mentioned in the question
            - Format with table.column references
            - For location queries: Delhi → WHERE LOCATION_ID = 'IN01'
            - Use ILIKE with % wildcards for case-insensitive text matching
            - Use exact column names as shown in schema
            - Follow the grain and primary key constraints
            - Don't select table name in quotes
            - Consider business rules when filtering or grouping data

            **Response Format:**
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

        try:
            response = await self.client.chat.completions.create(
                model=self.LLM_model,
                messages=[{"role": "system", "content": system_prompt}],
                # temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # If SQL query was generated, execute it
            # if result.get("intent") == "sql_query" and result.get("sql_query"):

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
                else:
                    result["final_answer"] = f"I generated this SQL query but encountered an error: {query_result.get('error', 'Unknown error')}"
            else:
                result["final_answer"] = result["explanation"]
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating SQL response: {e}")
            return {
                "intent": "error",
                "explanation": f"I encountered an error while processing your query: {str(e)}",
                "final_answer": "I'm sorry, I encountered an error while processing your request.",
                "confidence": 0.0
            }
    
    async def execute_sql_query(self, sql_query: str) -> Dict[str, Any]:
        """Safely execute SQL query"""
        if not db.pool:
            return {"success": False, "error": "Database not available"}
        
        # Basic SQL injection protection - only allow SELECT statements
        sql_upper = sql_query.strip().upper()
        # if not sql_upper.startswith('SELECT'):
        #     return {"success": False, "error": "Only SELECT queries are allowed"}
        
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
            reference_context = f"\n\nReferences: {', '.join(ref['content'][:200] for ref in relevant_data['references'])}..." if relevant_data['references'] else ""
        prompt = f"""You are a helpful assistant.

            The user asked: {user_query}
            SQL Query Executed:{sql_query}
            SQL Query Results: {json.dumps(query_results, indent=2, default=str)}
            The SQL query returned: {len(query_results)} rows
            Business Context: {business_context}
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
                tables_used=response.get("tables_used", [])
            )
        except Exception as e:
            logger.error(f"Error storing conversation: {e}")

    async def get_conversation_history(self, conversation_id: str, user_id: int) -> List[Dict]:
        """Get conversation history from database"""
        try:
            messages = await db.get_conversation_messages(conversation_id, user_id)
            
            # Convert to format expected by the chat
            conversation_history = []
            for msg in messages:
                conversation_history.append({
                    'role': msg['role'],
                    'content': msg['content'],
                    'sql_query': msg.get('sql_query'),
                    'intent': msg.get('intent'),
                    'timestamp': msg['created_at']
                })
            
            return conversation_history
        except Exception as e:
            logger.error(f"Error fetching conversation history: {e}")
            return []
        
    # async def store_conversation(self, user_id: int, project_id: str, query: str, response: Dict):
    #     """Store conversation for context in future queries"""
    #     conversation_key = f"{user_id}_{project_id}"
        
    #     if conversation_key not in self.conversation_memory:
    #         self.conversation_memory[conversation_key] = []
        
    #     # Add user message
    #     self.conversation_memory[conversation_key].append({
    #         "role": "user",
    #         "content": query,
    #         "timestamp": asyncio.get_event_loop().time()
    #     })
        
    #     # Add assistant response
    #     # Add assistant response with enhanced context
    #     assistant_message = {
    #         "role": "assistant",
    #         "content": response.get("final_answer", response.get("explanation", "")),
    #         "intent": response.get("intent"),
    #         "timestamp": asyncio.get_event_loop().time()
    #     }
        
    #     # Include SQL query and results if available
    #     if response.get("sql_query"):
    #         assistant_message["sql_query"] = response["sql_query"]
    #         assistant_message["tables_used"] = response.get("tables_used", [])
    #         assistant_message["business_rules_applied"] = response.get("business_rules_applied", [])
            
    #     if response.get("query_result"):
    #         # Store a summary of results, not full data
    #         result_summary = {
    #             "success": response["query_result"].get("success"),
    #             "row_count": response["query_result"].get("row_count", 0),
    #             "error": response["query_result"].get("error") if not response["query_result"].get("success") else None
    #         }
    #         assistant_message["query_result_summary"] = result_summary
        
    #     self.conversation_memory[conversation_key].append(assistant_message)
        
    #     # Keep only last 20 messages to manage memory
    #     if len(self.conversation_memory[conversation_key]) > 20:
    #         self.conversation_memory[conversation_key] = self.conversation_memory[conversation_key][-20:]
    
    # async def get_conversation_history(self, user_id: int, project_id: str) -> List[Dict]:
    #     """Get conversation history for context"""
    #     conversation_key = f"{user_id}_{project_id}"
    #     return self.conversation_memory.get(conversation_key, [])
    

    # **NEW: Intent Detection**
    async def detect_query_intent(self, user_query: str, conversation_history: List[Dict]) -> str:
        """Detect if user query is SQL-related, chit-chat, or clarification"""
        
        # Use LLM for complex cases
        context = ""
        if conversation_history:
            recent = [msg['content'][:50] for msg in conversation_history[-3:]]
            context = f"Recent conversation: {', '.join(recent)}"

        prompt = f"""Classify this user query into one of three categories:

            User Query: "{user_query}"
            {context}

            Categories:
            1. "sql_query" - User wants data analysis, database queries, or business insights
            2. "chit_chat" - User is greeting, thanking, or having general conversation
            3. "clarification" - User is asking for help or clarification about what they can do

            Examples:
            - "Hello" → chit_chat
            - "Show me sales data" → sql_query  
            - "What can you do?" → clarification
            - "Thanks!" → chit_chat
            - "How many customers do we have?" → sql_query

            Return only the category name (sql_query, chit_chat, or clarification)."""

        try:
            response = await self.client.chat.completions.create(
                model=self.NLP_LLM_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=10
            )
            
            intent = response.choices[0].message.content.strip().lower()
            return intent if intent in ['sql_query', 'chit_chat', 'clarification'] else 'sql_query'
            
        except Exception as e:
            logger.error(f"Intent detection failed: {e}")
            return 'sql_query'  # Default to SQL query

    # **NEW: Handle Chit-Chat**
    async def generate_chit_chat_response(self, user_query: str, conversation_history: List[Dict]) -> str:
        """Generate friendly conversational responses"""
        
        # Pattern-based responses for common cases
        query_lower = user_query.lower().strip()
        
        if any(greet in query_lower for greet in ['hi', 'hello', 'hey']):
            return "Hello! I'm your SQL Assistant. I can help you query your database and analyze your data. What would you like to know?"
        
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

        prompt = f"""You are a helpful and friendly SQL Assistant for a business intelligence platform.

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

    # **NEW: Handle Clarification Requests**
    async def generate_clarification_response(self, user_query: str, conversation_history: List[Dict]) -> str:
        """Handle questions about capabilities and help requests"""
        
        help_response = """I'm your SQL Assistant! Here's what I can help you with:

            🔍 **Data Queries**: Ask questions about your data in natural language
            - "Show me sales for last quarter"
            - "How many customers do we have?"
            - "What's the average order value?"

            📊 **Data Analysis**: Get insights and summaries
            - "Which products are performing best?"
            - "Show me trends in customer behavior"

            💬 **Follow-up Questions**: Build on previous queries
            - "Add a filter for region"
            - "Sort that by date"
            - "Show me more details"

            Just ask me anything about your data in plain English, and I'll convert it to SQL and run the analysis for you!"""

        query_lower = user_query.lower()
        if any(word in query_lower for word in ['help', 'what can you', 'how do i', 'what do you do']):
            return help_response
        
        return "I can help you query your database and analyze your data. Just ask me questions in natural language! For example: 'Show me sales data for last month' or 'How many customers do we have?'"

    # **ENHANCED: Main Query Processing**
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
            if intent == 'chit_chat':
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
                
                # Store nested (existing behavior)
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
