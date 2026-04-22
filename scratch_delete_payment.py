from sqlmodel import Session, select
from app.core.db import engine
from app.models import Payment
import uuid

def delete_pending_payment():
    payment_id = uuid.UUID("4f272f56-f618-4027-93ed-b6d3b898faf1")
    with Session(engine) as session:
        payment = session.get(Payment, payment_id)
        if payment:
            print(f"Deleting payment: {payment.id}, Amount: {payment.amount}, Desc: {payment.description}")
            session.delete(payment)
            session.commit()
            print("✅ Payment deleted successfully.")
        else:
            print("❌ Payment not found.")

if __name__ == "__main__":
    delete_pending_payment()
