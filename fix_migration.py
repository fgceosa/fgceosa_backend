with open("app/alembic/versions/e904d0db398c_phase2_fgceosa_schema.py", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "schema='copilot'" in line or "schema=\"copilot\"" in line:
        continue
    new_lines.append(line)

for i, line in enumerate(new_lines):
    if "def upgrade():" in line:
        new_lines.insert(i + 2, "    op.execute('DROP SCHEMA IF EXISTS copilot CASCADE')\n")
        break

with open("app/alembic/versions/e904d0db398c_phase2_fgceosa_schema.py", "w") as f:
    f.write("".join(new_lines))
