import re

with open("app/api/routes/users.py", "r") as f:
    code = f.read()

# Add back send_new_account_email
code = code.replace("from pydantic import", "from app.utils import send_new_account_email, send_email_verification\nfrom pydantic import")

# Dummy get_users_analytics
code = re.sub(r'def get_users_analytics\(session: SessionDep\) -> Any:.*?return \{.*?\}',
"""def get_users_analytics(session: SessionDep) -> Any:
    total_users = session.exec(select(func.count()).select_from(User)).one()
    active_users = session.exec(select(func.count()).select_from(User).where(User.status == "active")).one()
    return {"totalUsers": total_users, "activeUsers": active_users}""",
code, flags=re.DOTALL)

# Clean up read_users
code = re.sub(r'def read_users\(.*?return UsersPublic\(.*?data=public_users,.*?count=count.*?    \)', 
"""def read_users(
    session: SessionDep, 
    page: int = 1, 
    page_size: int = 100,
    search: str | None = None,
    sort_by: str | None = None,
    order: str | None = "asc"
) -> Any:
    statement = select(User).options(selectinload(User.user_roles))
    if search:
        search_filter = f"%{search}%"
        statement = statement.where((User.email.ilike(search_filter)) | (User.full_name.ilike(search_filter)))
    
    count_statement = select(func.count()).select_from(statement.subquery())
    count = session.exec(count_statement).one()
    
    skip = (page - 1) * page_size
    users = session.exec(statement.offset(skip).limit(page_size)).all()
    
    public_users = []
    for u in users:
        public_users.append(UserPublic.from_user(u))
        
    return UsersPublic(data=public_users, count=count)""",
code, flags=re.DOTALL)

with open("app/api/routes/users.py", "w") as f:
    f.write(code)
