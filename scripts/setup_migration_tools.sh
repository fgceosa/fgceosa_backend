#!/bin/bash
# One-time setup script for migration tools
# Run this once when setting up the project

set -e

echo "=========================================="
echo "Migration Tools Setup"
echo "=========================================="

# Check if we're in the right directory
if [ ! -f "alembic.ini" ]; then
    echo "❌ Error: alembic.ini not found. Run from project root."
    exit 1
fi

echo ""
echo "📦 Step 1: Installing pre-commit..."
if command -v pre-commit &> /dev/null; then
    echo "✅ pre-commit already installed"
else
    echo "Installing pre-commit..."
    pip install pre-commit
fi

echo ""
echo "📦 Step 2: Installing pre-commit hooks..."
pre-commit install
echo "✅ Pre-commit hooks installed"

echo ""
echo "📦 Step 3: Making scripts executable..."
chmod +x scripts/*.sh scripts/*.py
echo "✅ Scripts are now executable"

echo ""
echo "📦 Step 4: Running initial validation..."
python3 scripts/validate_migrations.py || true

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Available Commands:"
echo "  • Create migration:  ./scripts/create_migration.sh \"message\""
echo "  • Check for issues:  python3 scripts/auto_merge_migrations.py"
echo "  • Fix orphaned:      python3 scripts/fix_alembic_state.py"
echo ""
echo "📚 Read the full guide: MIGRATION_GUIDELINES.md"
echo ""
