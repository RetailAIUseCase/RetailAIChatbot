"""
Database connection and operations
"""
import asyncpg
from typing import List, Optional, Dict, Any
from app.config.settings import settings
import logging
# Import pgvector registration
from pgvector.asyncpg import register_vector

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
            
            # # Create users table if it doesn't exist
            # await self.create_users_table()

            # Create all tables
            await self.create_all_tables()
            
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

    async def create_all_tables(self):
        """Create all necessary tables"""
        basic_tables_query = """
                -- Enable required extensions FIRST
                CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
                CREATE EXTENSION IF NOT EXISTS vector;

                -- Users table (MUST BE FIRST - other tables reference this)
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                -- Projects table (SECOND - documents reference this)
                CREATE TABLE IF NOT EXISTS projects (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, name)
                );
                
                -- Documents table (THIRD - embedding tables reference this)
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
            """
        embedding_tables_query="""
                -- Metadata embeddings (schema tables, columns, relationships)
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

                -- Business logic embeddings (rules, workflows)
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

                -- Reference document embeddings (supporting materials)
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
                """
        indexes_query="""
                -- Create basic indexes
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
                CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);
                CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
                
                -- Metadata embedding indexes
                CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_document_id ON metadata_embeddings(document_id);
                CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_project_id ON metadata_embeddings(project_id);
                CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_user_id ON metadata_embeddings(user_id);
                
                -- Business logic embedding indexes
                CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_document_id ON business_logic_embeddings(document_id);
                CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_project_id ON business_logic_embeddings(project_id);
                CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_user_id ON business_logic_embeddings(user_id);
                
                -- Reference embedding indexes
                CREATE INDEX IF NOT EXISTS idx_reference_embeddings_document_id ON reference_embeddings(document_id);
                CREATE INDEX IF NOT EXISTS idx_reference_embeddings_project_id ON reference_embeddings(project_id);
                CREATE INDEX IF NOT EXISTS idx_reference_embeddings_user_id ON reference_embeddings(user_id);

                -- Vector search indexes (Create after tables exist)
                CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_hnsw 
                ON metadata_embeddings USING hnsw(embedding vector_cosine_ops) 
                WITH (m = 16, ef_construction = 64);
                
                CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_hnsw 
                ON business_logic_embeddings USING hnsw(embedding vector_cosine_ops) 
                WITH (m = 16, ef_construction = 64);
                
                CREATE INDEX IF NOT EXISTS idx_reference_embeddings_hnsw 
                ON reference_embeddings USING hnsw(embedding vector_cosine_ops) 
                WITH (m = 16, ef_construction = 64);

                -- Enable RLS for security
                ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
                ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
                ALTER TABLE metadata_embeddings ENABLE ROW LEVEL SECURITY;
                ALTER TABLE business_logic_embeddings ENABLE ROW LEVEL SECURITY;
                ALTER TABLE reference_embeddings ENABLE ROW LEVEL SECURITY;
            
                -- Drop existing policies if they exist
                DROP POLICY IF EXISTS "users_own_projects" ON projects;
                DROP POLICY IF EXISTS "users_own_documents" ON documents;
                DROP POLICY IF EXISTS "users_own_metadata_embeddings" ON metadata_embeddings;
                DROP POLICY IF EXISTS "users_own_business_logic_embeddings" ON business_logic_embeddings;
                DROP POLICY IF EXISTS "users_own_reference_embeddings" ON reference_embeddings;

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
            """
                
        try:
            async with self.pool.acquire() as connection:
                logger.info("Creating basic tables...")
                await connection.execute(basic_tables_query)
                
                logger.info("Creating embedding tables...")
                await connection.execute(embedding_tables_query)
                
                logger.info("Creating indexes...")
                await connection.execute(indexes_query)
                
                logger.info("All tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    
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

    
# Global database instance
db = Database()
    


#async def create_all_tables(self):
        # """Create all necessary tables with working syntax"""
        
        # try:
        #     async with self.pool.acquire() as connection:
        #         # Step 1: Enable extensions
        #         logger.info("Enabling extensions...")
        #         await connection.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        #         await connection.execute('CREATE EXTENSION IF NOT EXISTS vector;')
                
        #         # Step 2: Create users table
        #         logger.info("Creating users table...")
        #         await connection.execute("""
        #             CREATE TABLE IF NOT EXISTS users (
        #                 id SERIAL PRIMARY KEY,
        #                 email VARCHAR(255) UNIQUE NOT NULL,
        #                 hashed_password VARCHAR(255) NOT NULL,
        #                 full_name VARCHAR(255),
        #                 is_active BOOLEAN DEFAULT TRUE,
        #                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        #                 updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        #             );
        #         """)
                
        #         # Step 3: Create projects table
        #         logger.info("Creating projects table...")
        #         await connection.execute("""
        #             CREATE TABLE IF NOT EXISTS projects (
        #                 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        #                 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        #                 name VARCHAR(255) NOT NULL,
        #                 description TEXT,
        #                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        #                 updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        #                 UNIQUE(user_id, name)
        #             );
        #         """)
                
        #         # Step 4: Create documents table
        #         logger.info("Creating documents table...")
        #         await connection.execute("""
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
        #                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        #                 updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        #             );
        #         """)
                
               
        #         # Step 6: Create embedding tables
        #         logger.info("Creating metadata_embeddings table...")
        #         await connection.execute("""
        #             CREATE TABLE IF NOT EXISTS metadata_embeddings (
        #                 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        #                 document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        #                 project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        #                 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        #                 table_name VARCHAR(255),
        #                 content_type VARCHAR(50) NOT NULL CHECK (content_type IN ('table', 'column', 'relationship')),
        #                 content TEXT NOT NULL,
        #                 embedding vector(1536),
        #                 metadata JSONB,
        #                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        #             );
        #         """)
                
                
        #         logger.info("Creating business_logic_embeddings table...")
        #         await connection.execute("""
        #             CREATE TABLE IF NOT EXISTS business_logic_embeddings (
        #                 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        #                 document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        #                 project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        #                 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        #                 rule_number INTEGER,
        #                 content TEXT NOT NULL,
        #                 embedding vector(1536),
        #                 metadata JSONB,
        #                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        #             );
        #         """)
                
        #         logger.info("Creating reference_embeddings table...")
        #         await connection.execute("""
        #             CREATE TABLE IF NOT EXISTS reference_embeddings (
        #                 id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        #                 document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        #                 project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        #                 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        #                 chunk_index INTEGER NOT NULL,
        #                 content TEXT NOT NULL,
        #                 embedding vector(1536),
        #                 metadata JSONB,
        #                 created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        #                 UNIQUE (document_id, user_id, project_id, chunk_index)
        #             );
        #         """)
                
        #         # Step 6: Verify tables exist before creating indexes
        #         logger.info("Verifying table structure...")
        #         tables_to_check = ['projects', 'documents', 'metadata_embeddings', 'business_logic_embeddings', 'reference_embeddings']
                
        #         for table in tables_to_check:
        #             result = await connection.fetchval("""
        #                 SELECT EXISTS (
        #                     SELECT FROM information_schema.columns 
        #                     WHERE table_name = $1 AND column_name = 'user_id'
        #                 );
        #             """, table)
                    
        #             if table != 'users' and not result:
        #                 logger.error(f"Table {table} is missing user_id column!")
        #                 raise Exception(f"Table {table} is missing user_id column")
                
        #         # Step 9: Create basic indexes
        #         logger.info("Creating indexes...")
        #         await connection.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        #         await connection.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);")
        #         await connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);")
        #         await connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);")
        #         await connection.execute("CREATE INDEX IF NOT EXISTS idx_metadata_embeddings_user_id ON metadata_embeddings(user_id);")
        #         await connection.execute("CREATE INDEX IF NOT EXISTS idx_business_logic_embeddings_user_id ON business_logic_embeddings(user_id);")
        #         await connection.execute("CREATE INDEX IF NOT EXISTS idx_reference_embeddings_user_id ON reference_embeddings(user_id);")
                
        #         # Step 10: Enable Row Level Security
        #         logger.info("Enabling Row Level Security...")
        #         await connection.execute("ALTER TABLE projects ENABLE ROW LEVEL SECURITY;")
        #         await connection.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY;")
        #         await connection.execute("ALTER TABLE metadata_embeddings ENABLE ROW LEVEL SECURITY;")
        #         await connection.execute("ALTER TABLE business_logic_embeddings ENABLE ROW LEVEL SECURITY;")
        #         await connection.execute("ALTER TABLE reference_embeddings ENABLE ROW LEVEL SECURITY;")
                
        #         # Step 11: Drop existing policies if they exist
        #         logger.info("Dropping existing RLS policies...")
        #         await connection.execute('DROP POLICY IF EXISTS "users_own_projects" ON projects;')
        #         await connection.execute('DROP POLICY IF EXISTS "users_own_documents" ON documents;')
        #         await connection.execute('DROP POLICY IF EXISTS "users_own_metadata_embeddings" ON metadata_embeddings;')
        #         await connection.execute('DROP POLICY IF EXISTS "users_own_business_logic_embeddings" ON business_logic_embeddings;')
        #         await connection.execute('DROP POLICY IF EXISTS "users_own_reference_embeddings" ON reference_embeddings;')
                
        #         # Step 12: Create RLS Policies
        #         logger.info("Creating RLS policies...")
        #         await connection.execute("""
        #             CREATE POLICY "users_own_projects" ON projects
        #             FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
        #         """)
                
        #         await connection.execute("""
        #             CREATE POLICY "users_own_documents" ON documents
        #             FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
        #         """)
                
        #         await connection.execute("""
        #             CREATE POLICY "users_own_metadata_embeddings" ON metadata_embeddings
        #             FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
        #         """)
                
        #         await connection.execute("""
        #             CREATE POLICY "users_own_business_logic_embeddings" ON business_logic_embeddings
        #             FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
        #         """)
                
        #         await connection.execute("""
        #             CREATE POLICY "users_own_reference_embeddings" ON reference_embeddings
        #             FOR ALL USING (user_id = current_setting('app.current_user_id', true)::integer);
        #         """)
                
        #         logger.info("All tables, constraints, and RLS policies created successfully")
        # except Exception as e:
        #     logger.error(f"Failed to create tables: {e}")
        #     raise