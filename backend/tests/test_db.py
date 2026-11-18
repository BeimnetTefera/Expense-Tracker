from app.db import get_connection, init_db

conn = get_connection("test_expenses.db")

init_db(conn)
init_db(conn)
tables = conn.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
""").fetchall()


for table in tables:
    print(table['name'])
    
    
conn.close()
    
    
