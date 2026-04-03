from sqlmodel import Session, select
from app.core.db import engine
from app.models import User

def get_user_tag(email: str):
    with Session(engine) as session:
        statement = select(User).where(User.email == email)
        results = session.exec(statement)
        user = results.first()
        if user:
            print(f"User found: {user.email}")
            print(f"Full Name: {user.full_name}")
            print(f"Tag Number: {user.tag_number}")
            return user.tag_number
        else:
            print(f"User with email {email} not found.")
            return None

if __name__ == "__main__":
    email = "engrjayt200@gmail.com"
    get_user_tag(email)
