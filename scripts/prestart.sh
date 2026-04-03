#! /usr/bin/env bash

set -e

# Base directory
cd "$(dirname "$0")/.."

# Let the DB start
python app/backend_pre_start.py

# Run migrations
alembic upgrade head

# Create initial data in DB
python app/initial_data.py

# Seed RBAC roles and permissions
export PYTHONPATH=$PYTHONPATH:.
python scripts/seed_hq_rbac.py
python scripts/seed_rbac_data.py

echo "✅ Prestart sequence completed successfully!"
