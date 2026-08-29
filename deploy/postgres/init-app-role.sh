#!/bin/sh
set -eu

database_password="$(tr -d '\r\n' < /run/secrets/database_password)"
if [ -z "$database_password" ]; then
    echo "The application database password is empty." >&2
    exit 1
fi

psql --set ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set app_user="${RAG_DATABASE_USER:-rag_app}" \
    --set app_database="$POSTGRES_DB" \
    --set app_password="$database_password" <<-'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE :"app_user"
    WITH LOGIN
    PASSWORD :'app_password'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION;
ALTER DATABASE :"app_database" OWNER TO :"app_user";
SQL
