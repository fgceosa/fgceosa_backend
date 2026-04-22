from sqlmodel import Session, select
from app.core.db import engine
from app.api.routes.dashboard import get_member_summary
from app.models import User
import json
from decimal import Decimal

class MockUser:
    def __init__(self, user):
        self.id = user.id
        self.status = user.status
        self.is_verified = user.is_verified
        self.membership_id = user.membership_id
        self.full_name = user.full_name
        self.first_name = user.first_name
        self.last_name = user.last_name
        self.email = user.email

def check_summary():
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == 'user@gmail.com')).first()
        if not user:
            print("No user found")
            return
            
        print(f"Checking summary for user: {user.email}")
        summary = get_member_summary(session, user)
        # Convert Decimals to float for JSON printing
        def dec_to_float(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, list):
                return [dec_to_float(i) for i in obj]
            if isinstance(obj, dict):
                return {k: dec_to_float(v) for k, v in obj.items()}
            return obj
            
        print(json.dumps(dec_to_float(summary), indent=2))

if __name__ == "__main__":
    check_summary()
