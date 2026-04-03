import sys
import os

files = [
    "app/credit_repository.py",
    "app/services/wallet_service.py",
    "app/services/user_credit_service.py",
    "app/services/organization_credit_service.py",
    "app/api/routes/organization_credits.py",
    "scripts/seed_rbac_data.py",
    "scripts/seed_hq_rbac.py"
]

for file in files:
    try:
        with open(file, 'r') as f:
            content = f.read()
            compile(content, file, 'exec')
        print(f"✓ {file} compiled successfully")
    except Exception as e:
        print(f"✗ {file} failed: {e}")
        sys.exit(1)
