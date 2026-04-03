#!/usr/bin/env python3
"""
Projects Feature Verification Script

Verifies that all components of the Projects feature are properly set up.
Run this script to check if everything is correctly installed and configured.
"""
import sys
from pathlib import Path

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def check_file_exists(file_path: str, description: str) -> bool:
    """Check if a file exists"""
    path = Path(file_path)
    if path.exists():
        print(f"{GREEN}✓{RESET} {description}: {file_path}")
        return True
    else:
        print(f"{RED}✗{RESET} {description}: {file_path} (MISSING)")
        return False


def check_import(module_path: str, description: str) -> bool:
    """Check if a module can be imported"""
    try:
        parts = module_path.split(".")
        module = __import__(module_path)
        for part in parts[1:]:
            module = getattr(module, part)
        print(f"{GREEN}✓{RESET} {description}: {module_path}")
        return True
    except ImportError as e:
        print(f"{RED}✗{RESET} {description}: {module_path} (IMPORT ERROR: {e})")
        return False
    except Exception as e:
        print(f"{YELLOW}⚠{RESET} {description}: {module_path} (WARNING: {e})")
        return True


def check_dependency(package_name: str) -> bool:
    """Check if a package is installed"""
    try:
        __import__(package_name)
        print(f"{GREEN}✓{RESET} Dependency: {package_name}")
        return True
    except ImportError:
        print(f"{RED}✗{RESET} Dependency: {package_name} (NOT INSTALLED)")
        return False


def verify_models():
    """Verify model definitions"""
    print(f"\n{BLUE}=== Checking Models ==={RESET}")
    checks = []

    try:
        from app.models import (
            Project,
            ProjectCreate,
            ProjectUpdate,
            ProjectPublic,
            Organization,
            OrganizationMember,
            ProjectStatus,
            ProjectType,
            UsageMetricsSummary,
            UsageTrendData,
            RecentAPICall,
            ProjectUsageResponse,
        )

        print(f"{GREEN}✓{RESET} All project models imported successfully")

        # Check model attributes
        project_attrs = ["name", "type", "status", "owner_user_id", "org_id", "api_key_id"]
        missing = [attr for attr in project_attrs if not hasattr(Project, attr)]

        if not missing:
            print(f"{GREEN}✓{RESET} Project model has all required attributes")
        else:
            print(f"{RED}✗{RESET} Project model missing attributes: {missing}")
            return False

        return True

    except ImportError as e:
        print(f"{RED}✗{RESET} Failed to import models: {e}")
        return False


def verify_service_layer():
    """Verify service layer"""
    print(f"\n{BLUE}=== Checking Service Layer ==={RESET}")

    try:
        from app.services import project_service

        required_functions = [
            "create_project",
            "update_project",
            "delete_project",
            "get_user_projects",
            "get_project_usage",
            "compute_usage_metrics",
            "check_project_access",
            "validate_api_key",
        ]

        missing = [func for func in required_functions if not hasattr(project_service, func)]

        if not missing:
            print(f"{GREEN}✓{RESET} All service functions available")
            return True
        else:
            print(f"{RED}✗{RESET} Missing service functions: {missing}")
            return False

    except ImportError as e:
        print(f"{RED}✗{RESET} Failed to import project_service: {e}")
        return False


def verify_routes():
    """Verify API routes"""
    print(f"\n{BLUE}=== Checking API Routes ==={RESET}")

    try:
        from app.api.routes import projects

        if hasattr(projects, "router"):
            print(f"{GREEN}✓{RESET} Projects router exists")

            # Check endpoints
            routes = [route.path for route in projects.router.routes]
            expected_routes = ["", "/{project_id}", "/{project_id}/usage"]

            missing_routes = [r for r in expected_routes if not any(r in route for route in routes)]

            if not missing_routes:
                print(f"{GREEN}✓{RESET} All expected routes defined: {len(routes)} routes")
                for route in routes:
                    print(f"  - {route}")
                return True
            else:
                print(f"{RED}✗{RESET} Missing routes: {missing_routes}")
                return False
        else:
            print(f"{RED}✗{RESET} Projects router not found")
            return False

    except ImportError as e:
        print(f"{RED}✗{RESET} Failed to import projects routes: {e}")
        return False


def verify_migration():
    """Verify migration file"""
    print(f"\n{BLUE}=== Checking Database Migration ==={RESET}")

    migration_file = "app/alembic/versions/add_enhanced_projects_feature.py"
    if check_file_exists(migration_file, "Migration file"):
        try:
            with open(migration_file, "r") as f:
                content = f.read()
                if "def upgrade():" in content and "def downgrade():" in content:
                    print(f"{GREEN}✓{RESET} Migration has upgrade() and downgrade() functions")
                    return True
                else:
                    print(f"{RED}✗{RESET} Migration missing required functions")
                    return False
        except Exception as e:
            print(f"{RED}✗{RESET} Error reading migration file: {e}")
            return False
    return False


def verify_dependencies():
    """Verify required dependencies"""
    print(f"\n{BLUE}=== Checking Dependencies ==={RESET}")

    required = ["validators", "fastapi", "sqlmodel", "pydantic"]
    results = [check_dependency(pkg) for pkg in required]

    return all(results)


def main():
    """Main verification function"""
    print(f"{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}Projects Feature Verification Script{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")

    results = {
        "Dependencies": verify_dependencies(),
        "Models": verify_models(),
        "Service Layer": verify_service_layer(),
        "API Routes": verify_routes(),
        "Migration": verify_migration(),
    }

    # Summary
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}Summary{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")

    all_passed = True
    for component, passed in results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"{component}: {status}")
        all_passed = all_passed and passed

    print(f"{BLUE}{'=' * 60}{RESET}")

    if all_passed:
        print(f"\n{GREEN}✓ All checks passed!{RESET}")
        print(f"\n{BLUE}Next steps:{RESET}")
        print(f"1. Install dependencies: {YELLOW}uv pip install -e .{RESET}")
        print(f"2. Run migration: {YELLOW}alembic upgrade head{RESET}")
        print(f"3. Start server: {YELLOW}python -m app.main{RESET}")
        print(f"4. Check docs: {YELLOW}http://localhost:8000/docs{RESET}")
        return 0
    else:
        print(f"\n{RED}✗ Some checks failed. Please fix the issues above.{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
