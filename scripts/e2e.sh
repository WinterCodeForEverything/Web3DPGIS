#!/usr/bin/env bash
# Browser end-to-end test in a throwaway environment: its own database, media folder, queue and server.
# Needs PostgreSQL + PostGIS, a Redis-compatible broker (Valkey), the converters, Node and Chrome.
#
#   scripts/e2e.sh                 # uses .env for database credentials if it exists
#   E2E_PORT=8800 scripts/e2e.sh   # other settings: E2E_DB, E2E_BROKER_URL, CHROME_PATH, E2E_ARTIFACTS, E2E_SKIP_BUILD
set -euo pipefail

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$ROOT"
if [ -f .env ]; then set -a; source .env; set +a; fi

PY="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY="$( command -v python3 )"
PORT="${E2E_PORT:-8799}"
export POSTGRES_DB="${E2E_DB:-southcloud_e2e}"
export MEDIA_ROOT="$( mktemp -d -t 3dpgis-e2e-media )"
export CELERY_BROKER_URL="${E2E_BROKER_URL:-redis://localhost:6379/15}"   # its own queue, away from development jobs
export CELERY_TASK_ALWAYS_EAGER=false
export STORAGE_BACKEND="${STORAGE_BACKEND:-local}"
export DJANGO_DEBUG=true
export DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost"
LOGS="${E2E_ARTIFACTS:-$ROOT/e2e-artifacts}"
mkdir -p "$LOGS"
PIDS=()

db() {   # run SQL against the maintenance database
	"$PY" - "$1" <<'EOF'
import os, sys, psycopg
with psycopg.connect( dbname = 'postgres', user = os.environ.get( 'POSTGRES_USER' ) or None, password = os.environ.get( 'POSTGRES_PASSWORD' ) or None,
		host = os.environ.get( 'POSTGRES_HOST', 'localhost' ), port = os.environ.get( 'POSTGRES_PORT', '5432' ), autocommit = True ) as conn:
	for statement in sys.argv[1].split( ';' ):
		if statement.strip():
			conn.execute( statement )
EOF
}

cleanup() {
	local status=$?
	for pid in "${PIDS[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; done
	wait 2>/dev/null || true
	db "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" || true
	rm -rf "$MEDIA_ROOT"
	exit $status
}
trap cleanup EXIT

echo "== database $POSTGRES_DB"
db "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE); CREATE DATABASE \"$POSTGRES_DB\""
POSTGRES_DB="$POSTGRES_DB" "$PY" -c "
import os, psycopg
with psycopg.connect( dbname = os.environ['POSTGRES_DB'], user = os.environ.get( 'POSTGRES_USER' ) or None, password = os.environ.get( 'POSTGRES_PASSWORD' ) or None,
		host = os.environ.get( 'POSTGRES_HOST', 'localhost' ), port = os.environ.get( 'POSTGRES_PORT', '5432' ), autocommit = True ) as conn:
	conn.execute( 'CREATE EXTENSION IF NOT EXISTS postgis' )"
"$PY" manage.py migrate -v0

if [ -z "${E2E_SKIP_BUILD:-}" ] || [ ! -f frontend/dist/index.html ]; then
	echo "== building the web app"
	( cd frontend && npm run build >/dev/null )
fi

echo "== starting worker and server on :$PORT"
"$PY" -m celery -A cloudplat worker -l warning >"$LOGS/worker.log" 2>&1 &
PIDS+=( $! )
"$PY" manage.py runserver "127.0.0.1:$PORT" --noreload >"$LOGS/server.log" 2>&1 &
PIDS+=( $! )
for _ in $( seq 1 60 ); do
	curl -sf -o /dev/null "http://127.0.0.1:$PORT/api/v1/auth/me/" && break
	sleep 0.5
done

echo "== browser test"
E2E_BASE_URL="http://127.0.0.1:$PORT" E2E_ARTIFACTS="$LOGS" node frontend/e2e/app.e2e.mjs
