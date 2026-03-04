#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  setup_db.sh — Auto-install PostgreSQL, create codemaxxx DB + user
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

DB_NAME="${CODEMAXXX_DB_NAME:-codemaxxx}"
DB_USER="${CODEMAXXX_DB_USER:-codemaxxx}"
DB_PASS="${CODEMAXXX_DB_PASS:-codemaxxx}"

info()  { printf '  \033[1;34mℹ\033[0m  %s\n' "$*"; }
ok()    { printf '  \033[1;32m✔\033[0m  %s\n' "$*"; }
warn()  { printf '  \033[1;33m⚠\033[0m  %s\n' "$*" >&2; }

# ── Install PostgreSQL ─────────────────────────────────────────────
install_postgres() {
  if command -v psql >/dev/null 2>&1; then
    ok "PostgreSQL already installed"
    return
  fi

  info "Installing PostgreSQL..."
  if command -v brew >/dev/null 2>&1; then
    brew install postgresql@17 2>/dev/null || brew install postgresql 2>/dev/null || true
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y -qq postgresql postgresql-client
  else
    warn "Cannot auto-install PostgreSQL — install manually"
    return 1
  fi
}

# ── Start PostgreSQL ──────────────────────────────────────────────
start_postgres() {
  if command -v brew >/dev/null 2>&1; then
    if ! brew services list 2>/dev/null | grep -q 'postgresql.*started'; then
      info "Starting PostgreSQL via brew services..."
      brew services start postgresql@17 2>/dev/null || brew services start postgresql 2>/dev/null || true
      sleep 2
    fi
    ok "PostgreSQL running"
  elif command -v systemctl >/dev/null 2>&1; then
    if ! systemctl is-active --quiet postgresql; then
      sudo systemctl start postgresql
    fi
    ok "PostgreSQL running"
  fi
}

# ── Create user + database ─────────────────────────────────────────
setup_database() {
  info "Creating database user '${DB_USER}'..."

  # Create user if not exists
  psql postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" 2>/dev/null | grep -q 1 || \
    psql postgres -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" 2>/dev/null || \
    sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" 2>/dev/null || true

  # Create database if not exists
  info "Creating database '${DB_NAME}'..."
  psql postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" 2>/dev/null | grep -q 1 || \
    psql postgres -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || \
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || true

  # Grant privileges
  psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" 2>/dev/null || \
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" 2>/dev/null || true

  ok "Database '${DB_NAME}' ready for user '${DB_USER}'"
}

# ── Main ──────────────────────────────────────────────────────────
main() {
  echo ""
  echo "  🗄️  CodeMaxxx Database Setup"
  echo "  ─────────────────────────────"
  echo ""
  install_postgres
  start_postgres
  setup_database
  echo ""
  ok "PostgreSQL ready for CodeMaxxx long-term memory"
  echo ""
}

main "$@"
