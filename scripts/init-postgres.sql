-- ═══════════════════════════════════════════════════════════════
-- AgroSight AI — PostgreSQL Initialization
-- ═══════════════════════════════════════════════════════════════
-- Creates extensions and sets up the database for production.
-- Runs automatically on first container startup.
-- ═══════════════════════════════════════════════════════════════

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- Full-text search support
CREATE EXTENSION IF NOT EXISTS "btree_gin";      -- Index optimization

-- Set timezone
SET timezone = 'UTC';

-- Create application schema (optional, for organization)
-- CREATE SCHEMA IF NOT EXISTS agrosight;

-- Set default privileges for future tables
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agrosight;

-- Optional: Create a read-only user for analytics
-- CREATE USER agrosight_read WITH PASSWORD 'change-me-read-only';
-- GRANT CONNECT ON DATABASE agrosight TO agrosight_read;
-- GRANT USAGE ON SCHEMA public TO agrosight_read;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO agrosight_read;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agrosight_read;
