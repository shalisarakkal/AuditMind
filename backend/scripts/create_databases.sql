-- Run this once, connected as your Postgres superuser (usually 'postgres').
-- Creates a dedicated role + two databases: one for dev, one for the
-- integration test suite (kept separate so pytest's create/drop-table
-- teardown never touches your dev data).

CREATE ROLE auditmind WITH LOGIN PASSWORD 'auditmind';

CREATE DATABASE auditmind OWNER auditmind;
CREATE DATABASE auditmind_test OWNER auditmind;

-- pgvector (for the RAG `documents` table). Extensions are per-database and
-- require superuser, so enable it in each DB here. Uses psql's \connect, so
-- run this file with psql (e.g. `psql -U postgres -f create_databases.sql`).
\connect auditmind
CREATE EXTENSION IF NOT EXISTS vector;

\connect auditmind_test
CREATE EXTENSION IF NOT EXISTS vector;
