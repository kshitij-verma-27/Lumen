import sqlite3

conn = sqlite3.connect('darkspot.db')
c = conn.cursor()
print("Registry sources:")
for r in c.execute("SELECT id, name FROM registry_sources LIMIT 5"):
    print(" ", r)
print("Entities:")
for r in c.execute("SELECT id, name FROM entities LIMIT 5"):
    print(" ", r)
conn.close()
