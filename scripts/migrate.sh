#!/bin/bash
# Pre-deploy migration script with automatic healing
# Handles multiple heads, orphaned migrations, and auto-merging

set -e  # Exit on error

echo "=================================="
echo "Starting database migration..."
echo "=================================="

# Setup Copilot Schema (pgvector extension and schema)
echo "Setting up Copilot schema and pgvector extension..."
if [ -f "scripts/setup_copilot_schema.sh" ]; then
    bash scripts/setup_copilot_schema.sh || echo "⚠️  Copilot schema setup failed (may already exist)"
fi

# Try to run migration normally first
echo "Attempting database upgrade..."
UPGRADE_OUTPUT=$(alembic upgrade head 2>&1 || true)
UPGRADE_EXIT=$?

if [ $UPGRADE_EXIT -eq 0 ]; then
    echo "✅ Migration completed successfully!"
    exit 0
fi

echo "Migration failed. Analyzing issue..."
echo "$UPGRADE_OUTPUT"

# Check for multiple heads error
if echo "$UPGRADE_OUTPUT" | grep -q "Multiple head revisions"; then
    echo ""
    echo "⚠️  Multiple heads detected!"
    echo ""

    # Try to auto-merge heads
    echo "🔧 Attempting automatic head merge..."

    # Create a timestamp-based merge migration
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    MERGE_RESULT=$(alembic merge -m "auto_merge_deployment_${TIMESTAMP}" heads 2>&1 || true)

    if echo "$MERGE_RESULT" | grep -q "Generating"; then
        echo "✅ Merge migration created automatically"
        echo "Now upgrading to merged head..."
        alembic upgrade head
        exit $?
    else
        # If auto-merge fails, try upgrading all heads
        echo "⚠️  Auto-merge failed, trying to upgrade all heads..."
        alembic upgrade heads
        exit $?
    fi
fi

# Check for orphaned revision error
if echo "$UPGRADE_OUTPUT" | grep -q "Can't locate revision"; then
    echo ""
    echo "⚠️  Orphaned migration detected in database!"
    echo "This happens when a migration was applied but the file doesn't exist."
    echo ""
    echo "Running state fix script..."

    # Check if fix script exists
    if [ -f "scripts/fix_alembic_state.py" ]; then
        python3 scripts/fix_alembic_state.py
    else
        echo "❌ Fix script not found. Please reset database manually."
        exit 1
    fi
else
    echo "❌ Unknown migration error:"
    echo "$UPGRADE_OUTPUT"
    exit 1
fi
