#!/bin/sh
set -eu

read_secret() {
    secret_path="$1"
    if [ ! -r "$secret_path" ]; then
        echo "Required secret is not readable: $secret_path" >&2
        exit 1
    fi
    secret_value="$(tr -d '\r\n' < "$secret_path")"
    if [ -z "$secret_value" ]; then
        echo "Required secret is empty: $secret_path" >&2
        exit 1
    fi
    printf '%s' "$secret_value"
}

if [ -d /run/secrets ]; then
    database_password="$(read_secret /run/secrets/database_password)"
    export RAG_DATABASE_URL="postgresql+psycopg://${RAG_DATABASE_USER:-rag_app}:${database_password}@${RAG_DATABASE_HOST:-database}:${RAG_DATABASE_PORT:-5432}/${RAG_DATABASE_NAME:-rag1}"
    export RAG_JWT_SECRET_KEY="$(read_secret /run/secrets/jwt_secret_key)"
    export DEEPSEEK_API_KEY="$(read_secret /run/secrets/deepseek_api_key)"
    export RAG_METRICS_BEARER_TOKEN="$(read_secret /run/secrets/metrics_bearer_token)"
fi

exec "$@"
