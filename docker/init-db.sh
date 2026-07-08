#!/bin/bash
# Creates the "recon" database for backwards compatibility.
# The primary database "recontool" is already created by the POSTGRES_DB env var.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE recon OWNER recon'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'recon')\gexec
EOSQL
