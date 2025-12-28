-- Initialize PostgreSQL extensions for Geopolitical Intelligence Platform
-- This script runs automatically when the container is first created

-- Enable pgvector extension for embedding similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- TimescaleDB is already enabled in the timescale/timescaledb image
-- Just verify it's available
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Create additional useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- For UUID generation
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- For fuzzy text search

-- Verify extensions are installed
DO $$
BEGIN
    RAISE NOTICE 'Installed extensions:';
END $$;

SELECT extname, extversion FROM pg_extension 
WHERE extname IN ('vector', 'timescaledb', 'uuid-ossp', 'pg_trgm');

-- Log completion
DO $$
BEGIN
    RAISE NOTICE 'Database initialization complete!';
END $$;
