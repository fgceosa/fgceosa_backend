import psycopg2
import os

# Connection details derived from psql command and config
# PGPASSWORD='qorebit@ai2025$' psql -h localhost -U qorebit_admin -d qorebit_db

DB_HOST = "localhost"
DB_NAME = "qorebit_db"
DB_USER = "qorebit_admin"
DB_PASS = "qorebit@ai2025$"
DB_PORT = "5432"

def cleanup():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT
        )
        cur = conn.cursor()

        tables = ["audit_log", "notification", "security_event"]
        
        print("--- STARTING CLEANUP ---")
        
        for table in tables:
            # Check existence
            cur.execute(f"SELECT to_regclass('public.{table}');")
            exists = cur.fetchone()[0]
            
            if exists:
                # Count before
                cur.execute(f"SELECT count(*) FROM {table};")
                count_before = cur.fetchone()[0]
                print(f"Table '{table}' has {count_before} rows.")
                
                # Truncate
                if count_before > 0:
                    print(f"Truncating '{table}'...")
                    cur.execute(f"TRUNCATE TABLE {table} CASCADE;")
                    conn.commit()
                    
                    # Count after
                    cur.execute(f"SELECT count(*) FROM {table};")
                    count_after = cur.fetchone()[0]
                    print(f"Table '{table}' now has {count_after} rows.")
                else:
                    print(f"Table '{table}' is already empty.")
            else:
                print(f"Table '{table}' does not exist.")

        print("--- CLEANUP COMPLETE ---")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    cleanup()
