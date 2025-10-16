"""
Database connection and operations
"""
import json
import token
import asyncpg
from typing import List, Optional, Dict, Any
from app.config.settings import settings
import logging
# Import pgvector registration
from pgvector.asyncpg import register_vector
import uuid
import decimal
from datetime import date, datetime, time, timedelta

logger = logging.getLogger(__name__)

class Database:
    """Database connection manager with connection pool"""
    
    def __init__(self):
        # self.connection: Optional[asyncpg.Connection] = None
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Establish database connection"""
        try:
            # self.connection = await asyncpg.connect(settings.DATABASE_URL)
            # Create connection pool instead of single connection
            print("Connecting to database:", settings.DATABASE_URL)
            # Create connection pool with pgvector registration
            async def init_connection(conn):
                await register_vector(conn)

            self.pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                min_size=1,
                max_size=10,
                command_timeout=60,
                server_settings={
                    'jit': 'off'
                },
                init=init_connection
            )
            logger.info("Database connection established")
            
            # Smart setup - only create what's missing
            await self.ensure_schema_ready()

            # # Create all tables
            # await self.create_all_tables()
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    async def disconnect(self):
        # """Close database connection"""
        # if self.connection:
        #     await self.connection.close()
        #     logger.info("Database connection closed")
    
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def ensure_schema_ready(self):
        """Ultra-fast schema setup with minimal database roundtrips"""
        try:
            async with self.pool.acquire() as connection:
                logger.info("Checking database schema...")
                
                # Extensions (always safe to run)
                await connection.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
                await connection.execute('CREATE EXTENSION IF NOT EXISTS vector;')
                
                # Single query to check ALL tables at once
                tables_to_check = ['users', 'projects', 'documents', 'conversations', 
                                'metadata_embeddings', 'business_logic_embeddings', 
                                'reference_embeddings', 'chat_messages',
                                'purchase_orders', 'po_line_items', 'po_approval_requests', 'po_workflows']
                
                existing_tables = await connection.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = ANY($1::text[])
                """, tables_to_check)
                
                existing_table_names = {row['table_name'] for row in existing_tables}
                missing_tables = set(tables_to_check) - existing_table_names
                
                # Create missing tables (in dependency order)
                if missing_tables:
                    await self._create_missing_tables(connection, missing_tables)
                
                # Single query to check ALL indexes at once
                indexes_to_check = [
                    'idx_users_email', 'idx_projects_user_id', 
                    'idx_documents_project_id', 'idx_documents_user_id',
                    'idx_metadata_embeddings_document_id', 'idx_metadata_embeddings_project_id', 'idx_metadata_embeddings_user_id',
                    'idx_business_logic_embeddings_document_id', 'idx_business_logic_embeddings_project_id', 'idx_business_logic_embeddings_user_id',
                    'idx_reference_embeddings_document_id', 'idx_reference_embeddings_project_id', 'idx_reference_embeddings_user_id',
                    'idx_metadata_embeddings_hnsw', 'idx_business_logic_embeddings_hnsw', 'idx_reference_embeddings_hnsw',
                    'idx_po_workflow_status', 
                    #'idx_notifications_user',
                    'idx_po_user_project', 'idx_po_status', 'idx_po_line_items_po_number', 'idx_po_order_date', 'idx_po_user_project_date',
                    'idx_po_approval_token'
                ]
                
                existing_indexes = await connection.fetch("""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE schemaname = 'public' AND indexname = ANY($1::text[])
                """, indexes_to_check)
                
                existing_index_names = {row['indexname'] for row in existing_indexes}
                missing_indexes = set(indexes_to_check) - existing_index_names
                
                # Create missing indexes
                if missing_indexes:
                    await self._create_missing_indexes(connection, missing_indexes)
                
                # Setup security
                await self._setup_security(connection)
                
                logger.info("✅ Database schema ready!")
                
        except Exception as e:
            logger.error(f"❌ Schema setup failed: {e}")
            raise

    async def _create_missing_tables(self, connection, missing_tables):
        """Create missing tables in correct dependency order"""
        
        # Order matters for foreign key constraints
        table_order = ['users', 'projects', 'documents', 'conversations', 
                    'metadata_embeddings', 'business_logic_embeddings', 
                    'reference_embeddings', 'chat_messages', 'purchase_orders', 'po_line_items', 'po_approval_requests', 'po_workflows']
        
        table_queries = {
            'users': """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """,
            'projects': """
                CREATE TABLE IF NOT EXISTS projects (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, name)
                );
            """,
            'documents': """
                CREATE TABLE IF NOT EXISTS documents (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    original_filename VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    bucket_name VARCHAR(100) NOT NULL,
                    file_size BIGINT,
                    mime_type VARCHAR(100),
                    document_type VARCHAR(50) NOT NULL CHECK (document_type IN ('metadata', 'businesslogic', 'references')),
                    upload_status VARCHAR(50) DEFAULT 'completed' CHECK (upload_status IN ('processing', 'completed', 'failed')),
                    embedding_status VARCHAR(50) DEFAULT 'pending' CHECK (embedding_status IN ('pending', 'processing', 'completed', 'failed')),
                    processing_details JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """,
            'conversations': """
                CREATE TABLE IF NOT EXISTS conversations (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    title VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """,
            'metadata_embeddings': """
                CREATE TABLE IF NOT EXISTS metadata_embeddings (
                        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    table_name VARCHAR(255),
                    content_type VARCHAR(50) NOT NULL CHECK (content_type IN ('table', 'column', 'relationship')),
                    content TEXT NOT NULL,
                    embedding vector(1536),
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """,
            'business_logic_embeddings': """
                CREATE TABLE IF NOT EXISTS business_logic_embeddings (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    rule_number INTEGER,
                    content TEXT NOT NULL,
                    embedding vector(1536),
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """,
            'reference_embeddings': """
                CREATE TABLE IF NOT EXISTS reference_embeddings (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector(1536),
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (document_id, user_id, project_id, chunk_index)
                );
            """,
            'chat_messages': """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    sql_query TEXT,
                    query_result JSONB,
                    intent TEXT,
                    metadata JSONB,
                    tables_used TEXT[],
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """,
            'purchase_orders':"""
                CREATE TABLE IF NOT EXISTS purchase_orders (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    po_number VARCHAR(50) UNIQUE NOT NULL,
                    workflow_id VARCHAR(255) UNIQUE,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
                    vendor_id VARCHAR(50) NOT NULL,
                    vendor_name VARCHAR(255) NOT NULL,
                    vendor_email VARCHAR(255) NOT NULL,
                    total_amount DECIMAL(15, 2) NOT NULL,
                    pdf_path VARCHAR(500),
                    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('generated', 'pending_approval', 'approved', 'rejected', 'sent_to_vendor')),
                    needs_approval BOOLEAN DEFAULT FALSE,
                    comment TEXT,
                    approved_by VARCHAR(255),
                    order_date DATE NOT NULL,
                    approved_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """,
            'po_line_items':"""
                CREATE TABLE IF NOT EXISTS po_line_items (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    po_number VARCHAR(50) REFERENCES purchase_orders(po_number) ON DELETE CASCADE,
                    matnr VARCHAR(50) NOT NULL,
                    matdesc VARCHAR(255),
                    matcat VARCHAR(50),
                    quantity INTEGER NOT NULL,
                    unit_cost DECIMAL(10, 2) NOT NULL,
                    total_cost DECIMAL(15, 2) NOT NULL,
                    vendor_id VARCHAR(50) NOT NULL,
                    order_number VARCHAR(50),
                    shortfall_reason TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """,
            'po_approval_requests':"""
                CREATE TABLE IF NOT EXISTS po_approval_requests (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    po_number VARCHAR(50) REFERENCES purchase_orders(po_number) ON DELETE CASCADE,
                    approver_email TEXT NOT NULL,
                    approval_token VARCHAR(255) UNIQUE NOT NULL,
                    token_expires_at TIMESTAMPTZ NOT NULL,
                    status VARCHAR(50) NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
                    comment TEXT,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                );
            """,
            # 'purchase_notifications': """
            #     CREATE TABLE IF NOT EXISTS purchase_notifications (
            #         id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            #         po_number VARCHAR(50) REFERENCES purchase_orders(po_number),
            #         user_id INTEGER REFERENCES users(id),
            #         notification_type VARCHAR(50) NOT NULL,
            #         message TEXT,
            #         timestamp TIMESTAMPTZ DEFAULT now()
            #     );
            # """,
            'po_workflows': """
                CREATE TABLE IF NOT EXISTS po_workflows (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    workflow_id VARCHAR(255) UNIQUE NOT NULL,
                    project_id UUID NOT NULL,
                    user_id INTEGER NOT NULL,
                    order_date DATE NOT NULL,
                    current_step INTEGER DEFAULT 1,
                    status VARCHAR(50) DEFAULT 'running', -- running, completed, failed
                    step_results JSONB,
                    error_message TEXT,
                    trigger_query TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """

        }
        
        for table in table_order:
            if table in missing_tables:
                logger.info(f"📦 Creating table: {table}")
                await connection.execute(table_queries[table])

    async def _create_missing_indexes(self, connection, missing_indexes):
        """Create missing indexes - basic first, then vector indexes"""
        
        index_queries = {
            'idx_users_email': "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
            'idx_projects_user_id': "CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);",
            'idx_documents_project_id': "CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);",
            'idx_documents_user_id': "CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);",
            'idx_metadata_embeddings_document_id': "CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_document_id ON metadata_embeddings(document_id);",
            'idx_metadata_embeddings_project_id': "CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_project_id ON metadata_embeddings(project_id);",
            'idx_metadata_embeddings_user_id': "CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_user_id ON metadata_embeddings(user_id);",
            'idx_business_logic_embeddings_document_id': "CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_document_id ON business_logic_embeddings(document_id);",
            'idx_business_logic_embeddings_project_id': "CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_project_id ON business_logic_embeddings(project_id);",
            'idx_business_logic_embeddings_user_id': "CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_user_id ON business_logic_embeddings(user_id);",
            'idx_reference_embeddings_document_id': "CREATE INDEX IF NOT EXISTS idx_reference_embeddings_document_id ON reference_embeddings(document_id);",
            'idx_reference_embeddings_project_id': "CREATE INDEX IF NOT EXISTS  idx_reference_embeddings_project_id ON reference_embeddings(project_id);",
            'idx_reference_embeddings_user_id': "CREATE INDEX IF NOT EXISTS  idx_reference_embeddings_user_id ON reference_embeddings(user_id);",
            'idx_metadata_embeddings_hnsw': "CREATE INDEX IF NOT EXISTS  idx_metadata_embeddings_hnsw ON metadata_embeddings USING hnsw(embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);",
            'idx_business_logic_embeddings_hnsw': "CREATE INDEX IF NOT EXISTS  idx_business_logic_embeddings_hnsw ON business_logic_embeddings USING hnsw(embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);",
            'idx_reference_embeddings_hnsw': "CREATE INDEX IF NOT EXISTS  idx_reference_embeddings_hnsw ON reference_embeddings USING hnsw(embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);",
            'idx_po_workflow_status': "CREATE INDEX IF NOT EXISTS idx_po_workflow_status ON po_workflows(workflow_id, status);",
            # 'idx_notifications_user': "CREATE INDEX IF NOT EXISTS idx_notifications_user ON purchase_notifications(user_id, timestamp);",
            'idx_po_user_project': "CREATE INDEX IF NOT EXISTS idx_po_user_project ON purchase_orders(user_id, project_id);",
            'idx_po_status': "CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status);",
            'idx_po_line_items_po_number': "CREATE INDEX IF NOT EXISTS idx_po_line_items_po_number ON po_line_items(po_number);",
            'idx_po_order_date': "CREATE INDEX IF NOT EXISTS idx_po_order_date ON purchase_orders(order_date);",
            'idx_po_user_project_date': "CREATE INDEX IF NOT EXISTS idx_po_user_project_date ON purchase_orders(user_id, project_id, order_date);",
            'idx_po_approval_token': "CREATE INDEX IF NOT EXISTS idx_po_approval_token ON po_approval_requests(approval_token);"
        }
        
        # Create basic indexes first (fast)
        vector_indexes = {'idx_metadata_embeddings_hnsw', 'idx_business_logic_embeddings_hnsw', 'idx_reference_embeddings_hnsw'}
        basic_indexes = missing_indexes - vector_indexes
        
        for idx in basic_indexes:
            logger.info(f"⚡ Creating index: {idx}")
            await connection.execute(index_queries[idx])
        
        # Create vector indexes last (slow)
        for idx in missing_indexes & vector_indexes:
            logger.info(f"🎯 Creating vector index: {idx}")
            await connection.execute(index_queries[idx])

    async def _setup_security(self, connection):
        """Setup RLS - single query execution"""
        await connection.execute("""
            -- Enable RLS for security
                ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
                ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
                ALTER TABLE metadata_embeddings ENABLE ROW LEVEL SECURITY;
                ALTER TABLE business_logic_embeddings ENABLE ROW LEVEL SECURITY;
                ALTER TABLE reference_embeddings ENABLE ROW LEVEL SECURITY;
                ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
                ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
                ALTER TABLE purchase_orders ENABLE ROW LEVEL SECURITY;
                ALTER TABLE po_line_items ENABLE ROW LEVEL SECURITY;
                ALTER TABLE po_approval_requests ENABLE ROW LEVEL SECURITY;
                ALTER TABLE po_workflows ENABLE ROW LEVEL SECURITY;
                -- ALTER TABLE purchase_notifications ENABLE ROW LEVEL SECURITY;
                ALTER TABLE po_approval_requests DROP CONSTRAINT unique_po_number;
                ALTER TABLE po_approval_requests ADD CONSTRAINT unique_po_number UNIQUE (po_number);

            
                -- Drop existing policies if they exist
                DROP POLICY IF EXISTS "users_own_projects" ON projects;
                DROP POLICY IF EXISTS "users_own_documents" ON documents;
                DROP POLICY IF EXISTS "users_own_metadata_embeddings" ON metadata_embeddings;
                DROP POLICY IF EXISTS "users_own_business_logic_embeddings" ON business_logic_embeddings;
                DROP POLICY IF EXISTS "users_own_reference_embeddings" ON reference_embeddings;
                DROP POLICY IF EXISTS "users_own_conversations" ON conversations;
                DROP POLICY IF EXISTS "users_own_chat_messages" ON chat_messages;
                DROP POLICY IF EXISTS "users_own_pos" ON purchase_orders;
                DROP POLICY IF EXISTS "users_own_po_lines" ON po_line_items;
                                 
                -- Create RLS Policies
                CREATE POLICY "users_own_projects" ON projects
                    FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);

                CREATE POLICY "users_own_documents" ON documents
                FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
                
                CREATE POLICY "users_own_metadata_embeddings" ON metadata_embeddings
                    FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
                    
                CREATE POLICY "users_own_business_logic_embeddings" ON business_logic_embeddings
                    FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);

                CREATE POLICY "users_own_reference_embeddings" ON reference_embeddings
                    FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);

                CREATE POLICY "users_own_conversations" ON conversations
                    FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);

                CREATE POLICY "users_own_chat_messages" ON chat_messages
                    FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
                
                CREATE POLICY "users_own_pos" ON purchase_orders
                    FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
                    
                CREATE POLICY "users_own_po_lines" ON po_line_items
                    FOR ALL USING (po_number IN (SELECT po_number FROM purchase_orders WHERE user_id = current_setting('app.current_user_id', true)::integer));
                                 
            """)
    
    # USER METHODS
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        query = "SELECT * FROM users WHERE email = $1"
        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, email)
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get user by email: {e}")
            raise

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        if not self.pool:
            raise Exception("Database pool not initialized")

        query = "SELECT * FROM users WHERE id = $1"
        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, user_id)
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get user by ID: {e}")
            raise

    async def create_user(self, email: str, hashed_password: str, full_name: str = None) -> Dict[str, Any]:
        """Create a new user"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        query = """
        INSERT INTO users (email, hashed_password, full_name) 
        VALUES ($1, $2, $3) 
        RETURNING *
        """
        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, email, hashed_password, full_name)
                return dict(row)
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise
    
    # NEW PROJECT METHODS
    async def create_project(self, user_id: int, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new project"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        query = """
        INSERT INTO projects (user_id, name, description) 
        VALUES ($1, $2, $3) 
        RETURNING id::text, user_id, name, description, 
                  created_at::text, updated_at::text
        """
        try:
            async with self.pool.acquire() as connection:
                # Set user context for RLS
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                row = await connection.fetchrow(query, user_id, name, description)
                return dict(row)
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise

    async def get_user_projects(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all projects for a user"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        query = """
        SELECT id::text, user_id, name, description, 
               created_at::text, updated_at::text 
        FROM projects 
        WHERE user_id = $1 
        ORDER BY created_at DESC
        """
        try:
            async with self.pool.acquire() as connection:
                # Set user context for RLS
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                rows = await connection.fetch(query, user_id)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get user projects: {e}")
            raise

    async def get_project_by_id(self, project_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific project by ID"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        query = """
        SELECT id::text, user_id, name, description, 
               created_at::text, updated_at::text 
        FROM projects 
        WHERE id = $1 AND user_id = $2
        """
        try:
            async with self.pool.acquire() as connection:
                # Set user context for RLS
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                row = await connection.fetchrow(query, project_id, user_id)
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get project: {e}")
            raise

    async def delete_project(self, project_id: str, user_id: int) -> bool:
        """Delete a project and all its associated documents"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        try:
            async with self.pool.acquire() as connection:
                # Set user context for RLS
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                # Start transaction for atomic operation
                async with connection.transaction():
                    # First, verify the project exists and belongs to the user
                    check_query = "SELECT id FROM projects WHERE id = $1 AND user_id = $2"
                    project_exists = await connection.fetchrow(check_query, project_id, user_id)
                    
                    if not project_exists:
                        logger.warning(f"Project {project_id} not found or doesn't belong to user {user_id}")
                        return False
                    
                    # Delete the project (CASCADE will handle documents)
                    delete_query = "DELETE FROM projects WHERE id = $1 AND user_id = $2"
                    result = await connection.execute(delete_query, project_id, user_id)
                    
                    # Check if deletion was successful
                    rows_deleted = int(result.split()[-1]) if result.startswith('DELETE') else 0
                    success = rows_deleted == 1
                    
                    if success:
                        logger.info(f"Successfully deleted project {project_id} for user {user_id}")
                    else:
                        logger.warning(f"No project deleted for project_id: {project_id}, user_id: {user_id}")
                    
                    return success
                    
        except Exception as e:
            logger.error(f"Failed to delete project {project_id}: {e}")
            raise

    async def get_user_project_by_name(self, user_id: int, project_name: str) -> Optional[Dict[str, Any]]:
        """Check if a project with the given name already exists for the user"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        query = """
        SELECT id::text, user_id, name, description, 
               created_at::text, updated_at::text 
        FROM projects 
        WHERE user_id = $1 AND name = $2
        """
        try:
            async with self.pool.acquire() as connection:
                # Set user context for RLS
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                row = await connection.fetchrow(query, user_id, project_name)
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to get project by name: {e}")
            raise
    
    # DOCUMENT METHODS

    # Add document creation method to Database class
    async def create_document(
        self,
        id: str,
        project_id: str,
        user_id: int,
        name: str,
        original_filename: str,
        file_path: str,
        bucket_name: str,
        file_size: int,
        mime_type: str,
        document_type: str
    ) -> Dict[str, Any]:
        """Create a document record"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        query = """
        INSERT INTO documents (
            id, project_id, user_id, name, original_filename, file_path,
            bucket_name, file_size, mime_type, document_type
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id::text, project_id::text, user_id, name, original_filename,
                file_path, bucket_name, file_size, mime_type, document_type, 
                upload_status, embedding_status, created_at::text
        """
        
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                row = await connection.fetchrow(
                    query, id, project_id, user_id, name, original_filename,
                    file_path, bucket_name, file_size, mime_type, document_type
                )
                return dict(row)
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            raise

    async def get_project_documents(self, project_id: str, user_id: int) -> List[Dict[str, Any]]:
        """Get all documents for a project"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        query = """
        SELECT id::text, project_id::text, name, original_filename, file_size,
            mime_type, document_type, upload_status, embedding_status,
            created_at::text
        FROM documents
        WHERE project_id = $1 AND user_id = $2
        ORDER BY created_at DESC
        """
        
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                rows = await connection.fetch(query, project_id, user_id)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get documents: {e}")
            raise

    async def get_project_document_counts_by_type(self, project_id: str, user_id: int) -> Dict[str, int]:
        """Get document counts grouped by type for a project"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        query = """
        SELECT document_type, COUNT(*) as count
        FROM documents 
        WHERE project_id = $1 AND user_id = $2
        GROUP BY document_type
        """
        
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                rows = await connection.fetch(query, project_id, user_id)
                
                # Convert to dictionary
                counts = {}
                for row in rows:
                    counts[row['document_type']] = row['count']
                
                return counts
                
        except Exception as e:
            logger.error(f"Failed to get document counts: {e}")
            return {}
    # Add to Database class
    async def get_project_embedding_status(self, project_id: str, user_id: int) -> Dict[str, Any]:
        """Get embedding processing status for a project"""
        if not self.pool:
            raise Exception("Database pool not initialized")
        
        query = """
        SELECT 
            document_type,
            embedding_status,
            COUNT(*) as count
        FROM documents 
        WHERE project_id = $1 AND user_id = $2 
        GROUP BY document_type, embedding_status
        """
        
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                rows = await connection.fetch(query, project_id, user_id)
                
                status = {
                    'total': 0,
                    'processing': 0,
                    'completed': 0,
                    'failed': 0,
                    'pending': 0
                }
                
                for row in rows:
                    status['total'] += row['count']
                    status[row['embedding_status']] += row['count']
                
                return status
        except Exception as e:
            logger.error(f"Error getting embedding status: {e}")
            return {'total': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'pending': 0}

    # CHAT MESSAGE METHODS
    async def create_conversation(self, user_id: int, project_id: str, title: str = None) -> Dict[str, Any]:
        """Create a new conversation"""
        if not self.pool:
            raise Exception("Database pool not initialized")

        query = """
        INSERT INTO conversations (user_id, project_id, title)
        VALUES ($1, $2, $3)
        RETURNING id::text, user_id, project_id, title, 
                created_at::text, updated_at::text
        """

        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                row = await connection.fetchrow(query, user_id, project_id, title)
                return dict(row)
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
            raise

    async def get_user_conversations(self, user_id: int, project_id: str = None) -> List[Dict[str, Any]]:
        """Get all conversations for a user, optionally filtered by project"""
        if not self.pool:
            raise Exception("Database pool not initialized")

        if project_id:
            query = """
            SELECT c.id::text, c.user_id, c.project_id::text, c.title, 
                c.created_at::text, c.updated_at::text, p.name as project_name,
                COUNT(m.id) as message_count
            FROM conversations c
            LEFT JOIN projects p ON c.project_id = p.id
            LEFT JOIN chat_messages m ON c.id = m.conversation_id
            WHERE c.user_id = $1 AND c.project_id = $2
            GROUP BY c.id, p.name
            ORDER BY c.updated_at DESC
            """
            params = [user_id, project_id]
        else:
            query = """
            SELECT c.id::text, c.user_id, c.project_id::text, c.title, 
                c.created_at::text, c.updated_at::text, p.name as project_name,
                COUNT(m.id) as message_count
            FROM conversations c
            LEFT JOIN projects p ON c.project_id = p.id
            LEFT JOIN chat_messages m ON c.id = m.conversation_id
            WHERE c.user_id = $1
            GROUP BY c.id, p.name
            ORDER BY c.updated_at DESC
            """
            params = [user_id]

        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                rows = await connection.fetch(query, *params)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get conversations: {e}")
            raise

    def universal_serializer(self, obj):
        """
        Universal serializer for JSON that handles all common PostgreSQL/Python data types
        """
        # Numeric types
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        
        # Date/Time types
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, time):
            return obj.isoformat()
        if isinstance(obj, timedelta):
            return obj.total_seconds()
        
        # UUID types
        if isinstance(obj, uuid.UUID):
            return str(obj)
        
        # Bytes/Binary types
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode('utf-8', errors='ignore')
        
        # Set types (convert to list)
        if isinstance(obj, set):
            return list(obj)
        
        # Complex numbers
        if isinstance(obj, complex):
            return {'real': obj.real, 'imag': obj.imag}
        
        # Range objects (PostgreSQL ranges)
        if hasattr(obj, 'lower') and hasattr(obj, 'upper'):  # Range objects
            return {'lower': obj.lower, 'upper': obj.upper, 'bounds': getattr(obj, 'bounds', '[]')}
        
        # Enum types
        if hasattr(obj, 'name') and hasattr(obj, 'value'):  # Enum objects
            return obj.value
        
        # Memory view objects
        if isinstance(obj, memoryview):
            return obj.tobytes().decode('utf-8', errors='ignore')
        
        # Default fallback - try str() conversion
        try:
            return str(obj)
        except Exception:
            logger.warning(f"Could not serialize object of type {type(obj)}: {obj}")
            return f"<Non-serializable: {type(obj).__name__}>"
        
    async def store_chat_message(
        self, 
        conversation_id: str, 
        user_id: int, 
        project_id: str,
        role: str, 
        content: str, 
        sql_query: str = None,
        query_result: dict = None,
        intent: str = None,
        metadata: dict = None,
        tables_used: List[str] = None
    ) -> Dict[str, Any]:
        """Store a chat message"""
        if not self.pool:
            raise Exception("Database pool not initialized")
            
        # Safe JSON serialization function
        def safe_json_dumps(data):
            if data is None:
                return None
            try:
                return json.dumps(data, default=self.universal_serializer, ensure_ascii=False) 
            except Exception as e:
                logger.error(f"Failed to serialize data: {e}")
                return json.dumps({"error": f"Serialization failed: {str(e)}"})
        query = """
        INSERT INTO chat_messages 
        (conversation_id, user_id, project_id, role, content, sql_query, query_result, intent, metadata, tables_used)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id::text, conversation_id::text, role, content, created_at::text
        """

        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                row = await connection.fetchrow(
                    query, conversation_id, user_id, project_id, role, content,
                    sql_query, safe_json_dumps(query_result) if query_result else None,
                    intent, safe_json_dumps(metadata), tables_used
                )
                
                # Update conversation timestamp
                await connection.execute(
                    "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                    conversation_id
                )
                
                return dict(row)
        except Exception as e:
            logger.error(f"Failed to store chat message: {e}")
            raise

    async def get_conversation_messages(self, conversation_id: str, user_id: int) -> List[Dict[str, Any]]:
        """Get all messages for a conversation"""
        if not self.pool:
            raise Exception("Database pool not initialized")

        query = """
        SELECT id::text, conversation_id::text, role, content, sql_query, 
            query_result, intent, metadata, tables_used, created_at::text
        FROM chat_messages
        WHERE conversation_id = $1 AND user_id = $2
        ORDER BY created_at ASC
        """

        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                rows = await connection.fetch(query, conversation_id, user_id)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get conversation messages: {e}")
            raise

    # PO CRUD Operations
    async def create_workflow(
        self, user_id: int, project_id: str, order_date: date, trigger_query: str = None
    ) -> Dict[str, Any]:
        """Create new workflow record"""
        try:
            # Ensure order_date is a date object
            if isinstance(order_date, str):
                order_date = datetime.strptime(order_date, '%Y-%m-%d').date()
            
            async with self.pool.acquire() as connection:
                workflow_id = f"wf_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_id}"
                initial_results = json.dumps({
                    "step_name": "workflow_created",
                    "trigger_query": trigger_query
                })
                result = await connection.fetchrow("""
                    INSERT INTO po_workflows (
                        workflow_id, user_id, project_id, order_date, 
                        trigger_query, status, current_step, step_results, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING workflow_id
                """, 
                    workflow_id, user_id, project_id, order_date,  # order_date is now proper date object
                    trigger_query, "running", 0, initial_results,
                    datetime.now(), datetime.now()
                )
                
                if result:
                    logger.info(f"✅ Created workflow: {workflow_id} for user {user_id}, project {project_id}, date {order_date}")
                    return {
                        "success": True,
                        "workflow_id": workflow_id,
                        "user_id": user_id,
                        "project_id": project_id,
                        "order_date": order_date.strftime('%Y-%m-%d')  # Convert back to string for JSON
                    }
                else:
                    return {"success": False, "error": "Failed to create workflow record"}
                
        except ValueError as e:
            logger.error(f"Invalid date format in create_workflow: {e}")
            return {"success": False, "error": f"Invalid date format: {order_date}"}
        except Exception as e:
            logger.error(f"Failed to create workflow: {e}")
            return {"success": False, "error": str(e)}


    async def update_workflow(self, workflow_id: str, step: int, status: str, results: Dict = None, error: str = None):
        """Update workflow progress"""
        query = """
        UPDATE po_workflows 
        SET current_step = $2, status = $3, step_results = $4, error_message = $5, updated_at = CURRENT_TIMESTAMP
        WHERE workflow_id = $1
        """
        
        try:
            results_json = json.dumps(results) if results is not None else None
            async with self.pool.acquire() as connection:
                await connection.execute(query, workflow_id, step, status, results_json, error)
        except Exception as e:
            logger.error(f"Failed to update workflow: {e}")

    async def insert_po(self, po_data: Dict[str, Any]) -> Optional[str]:
        """Insert purchase order"""

        query = """
        INSERT INTO purchase_orders (
            po_number, workflow_id, project_id, user_id, vendor_id, vendor_name, vendor_email,
            total_amount, status, needs_approval, order_date, pdf_path, created_at, updated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) 
        RETURNING id::text
        """
        
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {po_data['user_id']}")
                row = await connection.fetchrow(
                    query, 
                    po_data['po_number'], po_data['workflow_id'], po_data['project_id'],
                    po_data['user_id'], po_data['vendor_id'], po_data['vendor_name'],
                    po_data['vendor_email'], po_data['total_amount'], po_data['status'],
                    po_data['needs_approval'], self._convert_date_for_db(po_data['order_date']), po_data['pdf_path'],
                    po_data['created_at'], po_data['updated_at']
                )
                return str(row['id']) if row else None
        except Exception as e:
            logger.error(f"Failed to insert PO: {e}")
            raise

    async def insert_po_items(self, po_number: str, items: List[Dict]):
        """Insert PO line items (flexible for multiple material types)"""
        query = """
        INSERT INTO po_line_items (po_number, matnr, matdesc, matcat, quantity, unit_cost, total_cost, vendor_id, order_number, shortfall_reason, created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """
        
        try:
            async with self.pool.acquire() as connection:
                for item in items:
                    await connection.execute(
                        query, po_number, 
                        item.get('matnr'), 
                        item.get('matdesc'), 
                        item.get('matcat'),
                        item.get('quantity'), 
                        item.get('unit_cost'), 
                        item.get('total_cost'),
                        item.get('vendor_id'),
                        item.get('order_number'),
                        item.get('shortfall_reason'),
                        datetime.utcnow()
                    )
        except Exception as e:
            logger.error(f"Failed to insert PO items: {e}")
            raise

    async def delete_po(self, po_number: str) -> bool:
        """Delete PO record - used for cleanup when PO generation fails"""
        try:
            async with self.pool.acquire() as connection:
                # Delete PO items first (foreign key constraint)
                await connection.execute(
                    "DELETE FROM po_line_items WHERE po_number = $1", po_number
                )
                
                # Delete PO record
                result = await connection.execute(
                    "DELETE FROM purchase_orders WHERE po_number = $1", po_number
                )
                
                # Check if any rows were deleted
                deleted_count = int(result.split()[-1]) if result else 0
                
                if deleted_count > 0:
                    logger.info(f"✅ Cleanup: Deleted PO record: {po_number}")
                    return True
                else:
                    logger.warning(f"⚠️ Cleanup: No PO record found to delete: {po_number}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Cleanup error deleting PO {po_number}: {e}")
            return False

    async def fetch_pos_by_date(self, user_id: int, project_id: str, order_date: str) -> List[Dict]:
        """Fetch POs by date and project"""

        query = """
        SELECT po.po_number, po.vendor_name, po.total_amount, po.status, po.needs_approval, 
               po.pdf_path, po.order_date, po.created_at::text, po.updated_at::text, po.comment
        FROM purchase_orders po
        WHERE po.user_id = $1 AND po.project_id = $2 AND po.order_date = $3
        ORDER BY po.created_at DESC
        """
        
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                rows = await connection.fetch(query, user_id, project_id, self._convert_date_for_db(order_date))
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch POs: {e}")
            return []

    async def fetch_all_pos_by_project(self, user_id: int, project_id: str) -> List[Dict]:
        """Fetch all POs for a project"""
        query = """
        SELECT po.po_number, po.vendor_name, po.total_amount, po.status, po.needs_approval,
               po.pdf_path, po.order_date, po.created_at::text, po.updated_at::text
        FROM purchase_orders po
        WHERE po.user_id = $1 AND po.project_id = $2
        ORDER BY po.order_date DESC, po.created_at DESC
        """
        
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                rows = await connection.fetch(query, user_id, project_id)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch all POs: {e}")
            return []
        
    async def get_po_by_number(self, po_number: str) -> Optional[Dict]:
        """Get PO details by number"""
        query = """
        SELECT po_number, vendor_name, vendor_email, total_amount, status, 
            pdf_path, user_id, project_id, order_date, workflow_id
        FROM purchase_orders 
        WHERE po_number = $1
        """
        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, po_number)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get PO by number: {e}")
            return None

    async def get_po_details_with_items(self, po_number: str, user_id: int) -> Optional[Dict]:
        """Get detailed PO information with line items"""
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                po_details = await connection.fetchrow("""
                    SELECT po.po_number, po.vendor_name, po.vendor_email, po.total_amount, 
                        po.status, po.needs_approval, po.pdf_path, po.order_date, 
                        po.created_at::text, po.updated_at::text, po.comment,
                        po.workflow_id::text
                    FROM purchase_orders po
                    WHERE po.po_number = $1 AND po.user_id = $2
                """, po_number, user_id)
                
                if not po_details:
                    return None
                
                # Get PO items
                po_items = await connection.fetch("""
                    SELECT matnr, matdesc, matcat, quantity, unit_cost, total_cost
                    FROM po_line_items
                    WHERE po_number = $1
                """, po_number)
                
                result = dict(po_details)
                result['items'] = [dict(item) for item in po_items]
                
                return result
                
        except Exception as e:
            logger.error(f"Error getting PO details with items: {e}")
            return None
        
    async def get_pos_by_workflow(self, workflow_id: str, user_id: int) -> List[Dict]:
        """Get POs generated by a specific workflow"""
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                pos = await connection.fetch("""
                    SELECT po_number, vendor_name, total_amount, status, needs_approval,
                        pdf_path, created_at::text, updated_at::text
                    FROM purchase_orders 
                    WHERE workflow_id = $1 AND user_id = $2
                    ORDER BY created_at DESC
                """, workflow_id, user_id)
                
                return [dict(po) for po in pos]
                
        except Exception as e:
            logger.error(f"Error fetching workflow POs: {e}")
            return []
        
    async def update_po_status(self, po_number: str, status: str, rejection_reason: str = None):
        """Update PO status"""
        if rejection_reason:
            query = """
            UPDATE purchase_orders 
            SET status = $1, comment = $2, updated_at = CURRENT_TIMESTAMP 
            WHERE po_number = $3
            """
            params = [status, rejection_reason, po_number]
        else:
            query = """
            UPDATE purchase_orders 
            SET status = $1, updated_at = CURRENT_TIMESTAMP 
            WHERE po_number = $2
            """
            params = [status, po_number]
        
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(query, *params)
            logger.info(f"PO {po_number} status updated to {status}")
        except Exception as e:
            logger.error(f"Failed to update PO status: {e}")

    async def create_approval_request_with_token(
        self, 
        po_number: str, 
        approver_email: str, 
        approval_token: str,
        token_expires_at: datetime
    ) -> bool:
        """Create approval request with specific approver and token"""
        query = """
        INSERT INTO po_approval_requests (
            po_number, approver_email, approval_token, 
            token_expires_at, status
        ) VALUES ($1, $2, $3, $4, 'pending')
        ON CONFLICT (po_number) DO UPDATE SET
            approver_email = EXCLUDED.approver_email,
            approval_token = EXCLUDED.approval_token,
            token_expires_at = EXCLUDED.token_expires_at,
            status = 'pending',
            updated_at = CURRENT_TIMESTAMP
        """
        
        try:
            async with self.pool.acquire() as connection:
                # First verify this PO actually needs approval (exceeds threshold)
                po_check = await connection.fetchrow("""
                    SELECT total_amount, needs_approval 
                    FROM purchase_orders 
                    WHERE po_number = $1
                """, po_number)
                
                if not po_check or not po_check['needs_approval']:
                    logger.warning(f"Attempted to create approval request for PO {po_number} that doesn't need approval")
                    return False
                
                await connection.execute(
                    query, po_number, approver_email, approval_token, token_expires_at
                )
                
                logger.info(f"Approval request created for high-value PO {po_number} (${po_check['total_amount']:,.2f})")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create approval request with token: {e}")
            return False

    async def validate_approval_token(self, token: str) -> Optional[Dict]:
        """Validate approval token and return approval request details"""
        query = """
        SELECT ar.po_number, ar.approver_email as approver_email, 
            ar.status, ar.token_expires_at,
            po.vendor_name, po.total_amount, po.user_id, po.project_id
        FROM po_approval_requests ar
        JOIN purchase_orders po ON ar.po_number = po.po_number
        WHERE ar.approval_token = $1 AND ar.token_expires_at > CURRENT_TIMESTAMP
        AND ar.status = 'pending'
        """
        
        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, token)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to validate approval token: {e}")
            return None
        

    async def update_approval_request(self, po_number: str, status: str, user_id: str, comment: str = None):
        """Update approval request status"""
        try:
            async with self.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                query = """
                UPDATE po_approval_requests 
                SET status = $1, comment = $2, updated_at = CURRENT_TIMESTAMP
                WHERE po_number = $3
                """
                await connection.execute(query, status, comment, po_number)
        except Exception as e:
            logger.error(f"Failed to update approval request: {e}")

    async def process_approval_decision(
        self, 
        token: str, 
        decision: str, 
        approver_email: str, 
        comment: str = None
    ) -> Dict[str, Any]:
        """Process approval/rejection decision"""
        query = """
        UPDATE po_approval_requests 
        SET status = $2, comment = $3, updated_at = CURRENT_TIMESTAMP
        WHERE approval_token = $1 AND approver_email = $4
        AND status = 'pending' AND token_expires_at > CURRENT_TIMESTAMP
        RETURNING po_number
        """

        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, token, decision, comment, approver_email)
                
                if row:
                    po_number = row['po_number']
                    # Update PO status
                    await self.update_po_status(po_number, decision, comment)
                    # After successful update, invalidate token immediately
                    await connection.execute("UPDATE po_approval_requests SET approval_token = 'USED_' || approval_token WHERE approval_token = $1", token)
                    return {"success": True, "po_number": po_number}
                else:
                    return {"success": False, "error": "Invalid token or unauthorized approver"}
                    
        except Exception as e:
            logger.error(f"Failed to process approval decision: {e}")
            return {"success": False, "error": str(e)}

    async def get_workflow_status(self, workflow_id: str) -> Optional[Dict]:
        """Get workflow status"""
        query = """
        SELECT workflow_id::text, current_step, status, step_results, error_message, 
               created_at::text, updated_at::text
        FROM po_workflows 
        WHERE workflow_id = $1
        """
        
        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, workflow_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get workflow status: {e}")
            return None

    # Finance Manager Helper
    async def get_finance_manager(self) -> Optional[Dict]:
        """Get finance manager for approvals"""
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow("""
                SELECT emp_id, emp_name, emp_email_id 
                FROM staff_directory 
                WHERE role ILIKE '%finance%' AND is_active = 'Y'
                LIMIT 1
            """)
            return dict(row) if row else None
        
    def _convert_date_for_db(self, date_input):
        """Helper to convert string dates to date objects for database"""
        if isinstance(date_input, str):
            return datetime.strptime(date_input, '%Y-%m-%d').date()
        return date_input
# Global database instance
db = Database()

# async def create_all_tables(self):
#     """Create all necessary tables"""
#     basic_tables_query = """
#             -- Enable required extensions FIRST
#             CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
#             CREATE EXTENSION IF NOT EXISTS vector;

#             -- Users table (MUST BE FIRST - other tables reference this)
#             CREATE TABLE IF NOT EXISTS users (
#                 id SERIAL PRIMARY KEY,
#                 email VARCHAR(255) UNIQUE NOT NULL,
#                 hashed_password VARCHAR(255) NOT NULL,
#                 full_name VARCHAR(255),
#                 is_active BOOLEAN DEFAULT TRUE,
#                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                 updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
#             );

#             -- Projects table (SECOND - documents reference this)
#             CREATE TABLE IF NOT EXISTS projects (
#                 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#                 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#                 name VARCHAR(255) NOT NULL,
#                 description TEXT,
#                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                 updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                 UNIQUE(user_id, name)
#             );
        
#             -- Documents table (THIRD - embedding tables reference this)
#             CREATE TABLE IF NOT EXISTS documents (
#                 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#                 project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
#                 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#                 name VARCHAR(255) NOT NULL,
#                 original_filename VARCHAR(255) NOT NULL,
#                 file_path VARCHAR(500) NOT NULL,
#                 bucket_name VARCHAR(100) NOT NULL,
#                 file_size BIGINT,
#                 mime_type VARCHAR(100),
#                 document_type VARCHAR(50) NOT NULL CHECK (document_type IN ('metadata', 'businesslogic', 'references')),
#                 upload_status VARCHAR(50) DEFAULT 'completed' CHECK (upload_status IN ('processing', 'completed', 'failed')),
#                 embedding_status VARCHAR(50) DEFAULT 'pending' CHECK (embedding_status IN ('pending', 'processing', 'completed', 'failed')),
#                 processing_details JSONB,
#                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                 updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
#             );
#             CREATE TABLE IF NOT EXISTS conversations (
#                 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#                 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#                 project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
#                 title VARCHAR(255),
#                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                 updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
#             );
#         """
#     embedding_tables_query="""
#             -- Metadata embeddings (schema tables, columns, relationships)
#             CREATE TABLE IF NOT EXISTS metadata_embeddings (
#                     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#                     document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
#                     project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
#                     user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#                     table_name VARCHAR(255),
#                     content_type VARCHAR(50) NOT NULL CHECK (content_type IN ('table', 'column', 'relationship')),
#                     content TEXT NOT NULL,
#                     embedding vector(1536),
#                     metadata JSONB,
#                     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
#                 );

#             -- Business logic embeddings (rules, workflows)
#             CREATE TABLE IF NOT EXISTS business_logic_embeddings (
#                     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#                     document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
#                     project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
#                     user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#                     rule_number INTEGER,
#                     content TEXT NOT NULL,
#                     embedding vector(1536),
#                     metadata JSONB,
#                     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
#                 );

#             -- Reference document embeddings (supporting materials)
#             CREATE TABLE IF NOT EXISTS reference_embeddings (
#                     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#                     document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
#                     project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
#                     user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#                     chunk_index INTEGER NOT NULL,
#                     content TEXT NOT NULL,
#                     embedding vector(1536),
#                     metadata JSONB,
#                     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                     UNIQUE (document_id, user_id, project_id, chunk_index)
#                 );
#             """
#     chat_history_query="""
#             CREATE TABLE IF NOT EXISTS chat_messages (
#                 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#                 conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
#                 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
#                 project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
#                 role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
#                 content TEXT NOT NULL,
#                 sql_query TEXT,
#                 query_result JSONB,
#                 intent VARCHAR(100),
#                 tables_used TEXT[],
#                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
#             );
#             """
#     indexes_query="""
#             -- Create basic indexes
#             CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
#             CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
#             CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);
#             CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
        
#             -- Metadata embedding indexes
#             CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_document_id ON metadata_embeddings(document_id);
#             CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_project_id ON metadata_embeddings(project_id);
#             CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_user_id ON metadata_embeddings(user_id);
        
#             -- Business logic embedding indexes
#             CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_document_id ON business_logic_embeddings(document_id);
#             CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_project_id ON business_logic_embeddings(project_id);
#             CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_user_id ON business_logic_embeddings(user_id);
        
#             -- Reference embedding indexes
#             CREATE INDEX IF NOT EXISTS idx_reference_embeddings_document_id ON reference_embeddings(document_id);
#             CREATE INDEX IF NOT EXISTS idx_reference_embeddings_project_id ON reference_embeddings(project_id);
#             CREATE INDEX IF NOT EXISTS idx_reference_embeddings_user_id ON reference_embeddings(user_id);

#             -- Vector search indexes (Create after tables exist)
#             CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_hnsw 
#             ON metadata_embeddings USING hnsw(embedding vector_cosine_ops) 
#             WITH (m = 16, ef_construction = 64);
        
#             CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_hnsw 
#             ON business_logic_embeddings USING hnsw(embedding vector_cosine_ops) 
#             WITH (m = 16, ef_construction = 64);
        
#             CREATE INDEX IF NOT EXISTS idx_reference_embeddings_hnsw 
#             ON reference_embeddings USING hnsw(embedding vector_cosine_ops) 
#             WITH (m = 16, ef_construction = 64);

#             -- Enable RLS for security
#             ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
#             ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
#             ALTER TABLE metadata_embeddings ENABLE ROW LEVEL SECURITY;
#             ALTER TABLE business_logic_embeddings ENABLE ROW LEVEL SECURITY;
#             ALTER TABLE reference_embeddings ENABLE ROW LEVEL SECURITY;
#             ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
#             ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
    
#             -- Drop existing policies if they exist
#             DROP POLICY IF EXISTS "users_own_projects" ON projects;
#             DROP POLICY IF EXISTS "users_own_documents" ON documents;
#             DROP POLICY IF EXISTS "users_own_metadata_embeddings" ON metadata_embeddings;
#             DROP POLICY IF EXISTS "users_own_business_logic_embeddings" ON business_logic_embeddings;
#             DROP POLICY IF EXISTS "users_own_reference_embeddings" ON reference_embeddings;
#             DROP POLICY IF EXISTS "users_own_conversations" ON conversations;
#             DROP POLICY IF EXISTS "users_own_chat_messages" ON chat_messages;
#             -- Create RLS Policies
#             CREATE POLICY "users_own_projects" ON projects
#                 FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);

#             CREATE POLICY "users_own_documents" ON documents
#             FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
        
#             CREATE POLICY "users_own_metadata_embeddings" ON metadata_embeddings
#                 FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
            
#             CREATE POLICY "users_own_business_logic_embeddings" ON business_logic_embeddings
#                 FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);

#             CREATE POLICY "users_own_reference_embeddings" ON reference_embeddings
#                 FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);

#             CREATE POLICY "users_own_conversations" ON conversations
#                 FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);

#             CREATE POLICY "users_own_chat_messages" ON chat_messages
#                 FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
#         """
        
#     try:
#         async with self.pool.acquire() as connection:
#             logger.info("Creating basic tables...")
#             await connection.execute(basic_tables_query)
        
#             logger.info("Creating embedding tables...")
#             await connection.execute(embedding_tables_query)

#             logger.info("Creating chat history tables...")
#             await connection.execute(chat_history_query)
        
#             logger.info("Creating indexes...")
#             await connection.execute(indexes_query)
        
#             logger.info("All tables created successfully")
#     except Exception as e:
#         logger.error(f"Failed to create tables: {e}")
#         raise
