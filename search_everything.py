
import sys
from sqlalchemy import text
from sqlmodel import Session, create_engine
from app.core.config import settings

def search_everything(db_name=None, port=5432):
    uri = str(settings.SQLALCHEMY_DATABASE_URI)
    # Replace the port and DB part in the URI
    # URI format: postgresql+psycopg://user:pass@host:port/db
    import re
    uri = re.sub(r':\d+/', f':{port}/', uri)
    
    if db_name:
        parts = uri.split("/")
        parts[-1] = db_name
        uri = "/".join(parts)
    
    print(f"Connecting to: {uri}")
    try:
        engine = create_engine(uri)
        with Session(engine) as session:
            print("--- Organizations ---")
            try:
                result = session.execute(text("SELECT id, name, credits_balance FROM organization"))
                for row in result:
                    print(f"Org: {row[1]} (ID: {row[0]}), Balance: {row[2]}")
            except:
                print("No organization table.")
            
            print("\n--- Workspaces ---")
            try:
                result = session.execute(text("SELECT id, name, organization_id FROM workspace"))
                for row in result:
                    print(f"Workspace: {row[1]} (ID: {row[0]}), OrgID: {row[2]}")
            except:
                print("No workspace table.")

            print("\n--- Users ---")
            try:
                result = session.execute(text("SELECT email, organization_name, full_name, account_type FROM \"user\""))
                for row in result:
                    print(f"User: {row[0]}, Org: {row[1]}, Full: {row[2]}, Type: {row[3]}")
            except Exception as e:
                print(f"User list failed: {e}")

            print("\n--- Searching for transactions with amount 20 ---")
            try:
                result = session.execute(text("SELECT id, wallet_id, amount, transaction_type, description FROM wallet_transaction WHERE amount = 20 OR amount = -20"))
                for row in result:
                    print(f"WalletTX Match: ID={row[0]}, Wallet={row[1]}, Amt={row[2]}, Type={row[3]}, Desc={row[4]}")
                
                result = session.execute(text("SELECT id, organization_id, amount, transaction_type, description FROM organization_credit_transaction WHERE amount = 20 OR amount = -20"))
                for row in result:
                    print(f"OrgTX Match: ID={row[0]}, Org={row[1]}, Amt={row[2]}, Type={row[3]}, Desc={row[4]}")
                
                print("\n--- Searching for '20' in Audit Logs ---")
                # Using string search on meta_data JSON as text
                result = session.execute(text("SELECT timestamp, action, target_id, meta_data FROM audit_log WHERE CAST(meta_data AS TEXT) LIKE '%20%'"))
                for row in result:
                    print(f"Audit Match: {row[0]}, Action={row[1]}, Target={row[2]}, Meta={row[3]}")
                    
            except Exception as e:
                print(f"Search for 20 failed: {e}")

            print("\n--- Organization Credit Transactions ---")
            try:
                result = session.execute(text("SELECT created_at, organization_id, amount, transaction_type, description FROM organization_credit_transaction ORDER BY created_at DESC"))
                for row in result:
                    print(f"OrgTX: {row[0]}, Org={row[1]}, Amt={row[2]}, Type={row[3]}, Desc={row[4]}")
            except:
                print("No org credit transaction table.")

            print("\n--- Wallet Transactions ---")
            try:
                result = session.execute(text("SELECT created_at, amount, transaction_type, credit, debit, description FROM wallet_transaction ORDER BY created_at DESC LIMIT 5"))
                for row in result:
                    print(f"TX: {row[0]}, Amt: {row[1]}, Type: {row[2]}, C: {row[3]}, D: {row[4]}, Desc: {row[5]}")
            except:
                print("No wallet_transaction table.")

    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "qorebit_db"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5432
    search_everything(db, port)
