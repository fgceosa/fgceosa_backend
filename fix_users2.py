import re

with open("app/api/routes/users.py", "r") as f:
    content = f.read()

# Remove copilot_session dependencies
content = content.replace(", copilot_session: CopilotSessionDep", "")
content = content.replace("copilot_session: CopilotSessionDep, ", "")
content = content.replace("copilot_session: CopilotSessionDep", "")

# Remove OrganizationMember imports and usage since we deleted them
content = re.sub(r'from app.models import OrganizationMember\n?', '', content)
content = re.sub(r'is_org_admin = False.*?if not current_user.is_superuser:.*?if user == current_user or is_org_admin:', 'if user == current_user:', content, flags=re.DOTALL)

with open("app/api/routes/users.py", "w") as f:
    f.write(content)
