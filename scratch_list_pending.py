from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Payment

def check_all_pending():
    with Session(engine) as session:
        statement = select(User, Payment).join(Payment).where(Payment.status == "pending")
        results = session.exec(statement).all()
        print(f"Found {len(results)} pending payments")
        for user, payment in results:
            print(f"User: {user.email}, Amount: {payment.amount}, Date: {payment.created_at}")

if __name__ == "__main__":
    check_all_pending()
