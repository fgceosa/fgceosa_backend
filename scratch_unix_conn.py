import psycopg
try:
    conn = psycopg.connect("dbname=qorebit_db user=jamesoyanna host=/private/tmp")
    print("SUCCESSFULLY CONNECTED VIA UNIX DOMAIN SOCKET!")
    cur = conn.cursor()
    cur.execute("SELECT version();")
    print(cur.fetchone())
    conn.close()
except Exception as e:
    print("Error:", e)
