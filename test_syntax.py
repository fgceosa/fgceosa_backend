"""
Quick syntax check for workspace_service.py
Run this to verify there are no Python syntax errors before starting the server
"""

import sys
import py_compile

files_to_check = [
    "app/services/workspace_service.py",
    "app/models.py",
    "app/api/routes/workspace.py",
]

print("=" * 60)
print("Checking Python Syntax")
print("=" * 60)
print()

all_passed = True

for file_path in files_to_check:
    try:
        py_compile.compile(file_path, doraise=True)
        print(f"✅ {file_path} - OK")
    except py_compile.PyCompileError as e:
        print(f"❌ {file_path} - SYNTAX ERROR")
        print(f"   {e}")
        all_passed = False

print()
print("=" * 60)

if all_passed:
    print("✅ All files passed syntax check!")
    print("You can safely restart the backend server.")
    sys.exit(0)
else:
    print("❌ Some files have syntax errors!")
    print("Fix the errors before restarting the server.")
    sys.exit(1)
