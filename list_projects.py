
from sqlmodel import Session, select
from app.core.db import engine
from app.models import Project

def list_projects():
    with Session(engine) as session:
        projects = session.exec(select(Project)).all()
        for p in projects:
            print(f"Name: '{p.name}', ID: {p.id}, Org ID: {p.org_id}")

if __name__ == "__main__":
    list_projects()
