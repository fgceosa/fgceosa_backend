import sys
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User

def list_users():
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        for user in users:
            print(f"ID: {user.id}, Email: {user.email}, Name: {user.full_name}")

if __name__ == "__main__":
    list_users()
