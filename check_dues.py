from sqlmodel import Session, select
from app.core.db import engine
from app.models import Due, User, Payment

with Session(engine) as session:
    dues = session.exec(select(Due)).all()
    print(f"Total Dues: {len(dues)}")
    for d in dues:
        print(f"Due: {d.title}, Amount: {d.amount}, Active: {d.is_active}")
    
    users = session.exec(select(User)).all()
    print(f"Total Users: {len(users)}")
    
    payments = session.exec(select(Payment)).all()
    print(f"Total Payments: {len(payments)}")
