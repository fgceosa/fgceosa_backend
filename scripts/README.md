# Backend Scripts

This directory contains utility scripts for managing the Qorebit backend.

## Credit Workspace Script

### Python Script (Recommended)

The `credit_workspace.py` script allows you to manually add credits to any workspace.

**Usage:**

```bash
# Credit Devscourt AI workspace with 50 credits
python scripts/credit_workspace.py --workspace-name "Devscourt AI" --amount 50

# With custom description
python scripts/credit_workspace.py \
  --workspace-name "Devscourt AI" \
  --amount 50 \
  --description "Initial credits for testing"
```

**Prerequisites:**
- Make sure you're in the backend directory
- Virtual environment is activated (if using one)
- Database connection is properly configured in .env

**Example Output:**
```
============================================================
Manual Workspace Credit Addition
============================================================
Workspace: Devscourt AI
Amount: 50.0 credits
============================================================

✅ Found workspace: Devscourt AI (ID: 123e4567-e89b-12d3-a456-426614174000)
   Current balance: 0.00 credits
✅ Successfully credited 50.0 credits
   Old balance: 0.00 credits
   New balance: 50.00 credits
   Transaction ID: 789e4567-e89b-12d3-a456-426614174999

============================================================
✅ Operation completed successfully!
============================================================
```

### SQL Script (Alternative)

If the Python script doesn't work, you can use the SQL script `credit_devscourt_ai.sql`:

```bash
# Connect to your PostgreSQL database
psql -U your_username -d your_database_name

# Run the SQL script
\i scripts/credit_devscourt_ai.sql
```

Or using `psql` command directly:

```bash
psql -U your_username -d your_database_name -f scripts/credit_devscourt_ai.sql
```

## Notes

- The Python script automatically creates a transaction record
- The SQL script includes queries to verify the changes
- Both scripts add credits to the workspace's `credits_balance` field
- A transaction record is created with type `purchase` and status `completed`

## Troubleshooting

### Workspace Not Found
If you get "Workspace not found", verify the exact name:
```bash
# Check workspace names in database
psql -U your_username -d your_database_name -c "SELECT id, name, credits_balance FROM workspace;"
```

### Database Connection Error
Make sure your `.env` file has the correct database credentials:
```
DATABASE_URL=postgresql://user:password@localhost/dbname
```

### Permission Denied
Make sure the script has execute permissions:
```bash
chmod +x scripts/credit_workspace.py
```
