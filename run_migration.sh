#!/bin/bash

# Projects Feature Migration Script
# Automates the migration process with safety checks

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Projects Feature Migration Script${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Step 1: Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}✗ Error: pyproject.toml not found${NC}"
    echo -e "Please run this script from the qorebit-backend directory"
    exit 1
fi
echo -e "${GREEN}✓${NC} In correct directory\n"

# Step 2: Check Python version
echo -e "${BLUE}Checking Python version...${NC}"
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}✗ Python not found${NC}"
    echo -e "Please install Python 3.10 or higher"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION found\n"

# Step 3: Check if dependencies are installed
echo -e "${BLUE}Checking dependencies...${NC}"
if $PYTHON_CMD -c "import alembic" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Alembic is installed"
else
    echo -e "${YELLOW}⚠${NC} Alembic not found. Installing dependencies..."

    # Try to install dependencies
    if command -v uv &> /dev/null; then
        echo -e "${BLUE}Using uv to install dependencies...${NC}"
        uv pip install -e .
    else
        echo -e "${BLUE}Using pip to install dependencies...${NC}"
        $PYTHON_CMD -m pip install -e .
    fi

    echo -e "${GREEN}✓${NC} Dependencies installed"
fi
echo ""

# Step 4: Check database connection
echo -e "${BLUE}Checking database connection...${NC}"
if $PYTHON_CMD -c "from app.core.db import engine; engine.connect()" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Database connection successful\n"
else
    echo -e "${RED}✗ Database connection failed${NC}"
    echo -e "Please check your .env file and ensure PostgreSQL is running"
    exit 1
fi

# Step 5: Show current migration status
echo -e "${BLUE}Current migration status:${NC}"
$PYTHON_CMD -m alembic current
echo ""

# Step 6: Ask for confirmation
echo -e "${YELLOW}⚠ WARNING: This will modify your database schema${NC}"
echo -e "${YELLOW}   Make sure you have a backup!${NC}\n"

read -p "Do you want to proceed with the migration? (yes/no): " confirmation

if [ "$confirmation" != "yes" ]; then
    echo -e "\n${YELLOW}Migration cancelled${NC}"
    exit 0
fi

# Step 7: Preview migration (optional)
echo -e "\n${BLUE}Generating migration preview...${NC}"
$PYTHON_CMD -m alembic upgrade head --sql > migration_preview.sql 2>/dev/null || true
if [ -f "migration_preview.sql" ]; then
    echo -e "${GREEN}✓${NC} Preview saved to migration_preview.sql"
    echo -e "${BLUE}First 20 lines of SQL:${NC}"
    head -20 migration_preview.sql
    echo -e "\n${BLUE}...${NC}\n"
fi

# Step 8: Run the migration
echo -e "${BLUE}Running migration...${NC}"
$PYTHON_CMD -m alembic upgrade head

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✓ Migration completed successfully!${NC}\n"
else
    echo -e "\n${RED}✗ Migration failed${NC}"
    echo -e "Check the error messages above for details"
    exit 1
fi

# Step 9: Verify migration
echo -e "${BLUE}Verifying migration...${NC}"
$PYTHON_CMD -m alembic current
echo ""

# Step 10: Verify tables
echo -e "${BLUE}Verifying tables created...${NC}"
$PYTHON_CMD -c "
from app.core.db import engine
from sqlalchemy import inspect

inspector = inspect(engine)
tables = inspector.get_table_names()

required_tables = ['organization', 'organization_member', 'project']
all_present = True

for table in required_tables:
    if table in tables:
        print(f'  ✓ {table}')
    else:
        print(f'  ✗ {table} (MISSING)')
        all_present = False

if all_present:
    print('\n✓ All required tables present')
else:
    print('\n✗ Some tables are missing')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✓ All tables verified${NC}\n"
else
    echo -e "\n${RED}✗ Table verification failed${NC}"
    exit 1
fi

# Step 11: Run verification script (if it exists)
if [ -f "verify_projects_setup.py" ]; then
    echo -e "${BLUE}Running full verification script...${NC}\n"
    $PYTHON_CMD verify_projects_setup.py
fi

# Success message
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Migration completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "${BLUE}Next steps:${NC}"
echo -e "1. Start the server: ${YELLOW}$PYTHON_CMD -m app.main${NC}"
echo -e "2. Check API docs: ${YELLOW}http://localhost:8000/docs${NC}"
echo -e "3. Look for /projects endpoints\n"

echo -e "${GREEN}Your Projects feature is now live! 🚀${NC}\n"
