import sys
import os
sys.path.append(os.getcwd())
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, WalletOwnerType
from app.services.wallet_service import WalletService

def check_user_wallet():
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == 'onesphereng@gmail.com')).first()
        if not user:
            print("User not found")
            return
        
        wallet = WalletService.get_or_create_wallet(session, user.id, WalletOwnerType.USER)
        balance = WalletService.get_balance(session, wallet.id)
        print(f"User Personal Balance: {balance}")
        print(f"User Cached Credits: {user.credits}")

if __name__ == "__main__":
    check_user_wallet()
