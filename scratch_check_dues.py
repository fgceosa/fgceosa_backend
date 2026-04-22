from sqlmodel import Session, select
from app.core.db import engine
from app.models import Due, Payment

def check_dues():
    with Session(engine) as session:
        dues = session.exec(select(Due)).all()
        print(f"Total Dues: {len(dues)}")
        for d in dues:
            print(f"ID: {d.id}, Title: {d.title}, Amount: {d.amount}, Active: {d.is_active}, Date: {d.due_date}")
            
        payments = session.exec(select(Payment)).all()
        print(f"Total Payments: {len(payments)}")
        for p in payments:
            print(f"ID: {p.id}, Status: {p.status}, Amount: {p.amount}, Desc: {p.description}")

if __name__ == "__main__":
    check_dues()
