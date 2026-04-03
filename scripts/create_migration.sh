#!/bin/bash
# Safe migration creation script
# This wrapper ensures migrations are created safely without causing branch issues

set -e

echo "======================================"
echo "Safe Migration Creation Tool"
echo "======================================"

# Check if we're in the right directory
if [ ! -f "alembic.ini" ]; then
    echo "❌ Error: alembic.ini not found. Run from project root."
    exit 1
fi

# Get migration message from argument
MESSAGE="$1"

if [ -z "$MESSAGE" ]; then
    echo "❌ Error: Please provide a migration message"
    echo ""
    echo "Usage: ./scripts/create_migration.sh \"your migration message\""
    echo "Example: ./scripts/create_migration.sh \"add user profile table\""
    exit 1
fi

echo ""
echo "📋 Step 1: Checking for multiple heads..."
HEADS=$(alembic heads 2>&1 | grep -v "^$" | wc -l | tr -d ' ')

if [ "$HEADS" -gt 1 ]; then
    echo "⚠️  Multiple heads detected!"
    echo ""
    echo "You must merge heads before creating a new migration."
    echo "Run: python3 scripts/auto_merge_migrations.py"
    exit 1
fi

echo "✅ Single head confirmed"

echo ""
echo "📋 Step 2: Checking current migration status..."
alembic current

echo ""
echo "📋 Step 3: Generating migration..."
alembic revision --autogenerate -m "$MESSAGE"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Migration created successfully!"
    echo ""
    echo "📝 Next steps:"
    echo "  1. Review the generated migration file in app/alembic/versions/"
    echo "  2. Test it: alembic upgrade head"
    echo "  3. Commit it: git add app/alembic/versions/"
    echo "  4. Push it: git commit -m \"Add migration: $MESSAGE\" && git push"
    echo ""
    echo "⚠️  IMPORTANT: Always commit migration files immediately!"
else
    echo "❌ Migration creation failed"
    exit 1
fi
