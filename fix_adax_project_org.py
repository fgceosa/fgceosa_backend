
from sqlmodel import Session, select
from app.core.db import engine
from app.models import Project, Organization, User

def inspect_and_fix_project():
    with Session(engine) as session:
        # Find the project
        project = session.exec(select(Project).where(Project.name == "Adax")).first()
        if not project:
            print("Project 'Adax' not found.")
            return

        print(f"Project found: {project.name}, ID: {project.id}, Org ID: {project.org_id}")

        # Find the organization
        org = session.exec(select(Organization).where(Organization.email == "onesphereng@gmail.com")).first()
        if not org:
            print("Organization 'onesphereng@gmail.com' not found.")
            return

        print(f"Organization found: {org.name}, ID: {org.id}, Email: {org.email}")

        # Fix the project if it doesn't have an org_id
        if project.org_id is None:
            print("Project has no Organization ID. Updating...")
            project.org_id = org.id
            session.add(project)
            session.commit()
            session.refresh(project)
            print(f"Project updated. New Org ID: {project.org_id}")
        else:
            print("Project already has an Organization ID.")

if __name__ == "__main__":
    inspect_and_fix_project()
