import json
import sqlite3
class SqliteState:
    def __init__(self, path):
        self.path = path
        self.db = sqlite3.connect(self.path)
        self.c = self.db.cursor()

        self.setup()

    def setup(self):
        # Create table
        try :
            self.c.execute('''CREATE TABLE state (
                key text,
                value text
            )''')

            self.c.execute('''Create unique index if not exists idx_key on state(key)''')
            self.db.commit()
        except sqlite3.OperationalError:
            pass

    def get(self, key):
        key = key.lower()
        self.c.execute("select value from state where key=?", [key])
        records = self.c.fetchall()
        if records:
            return json.loads(records[0][0])
        return None

    def set(self, key, value):
        key = key.lower()
        value = json.dumps(value)
        self.c.execute("update state set value=? where key=?", [value, key])
        if not self.c.rowcount:
            self.c.execute("insert into state (key, value) VALUES (?,?)", [key, value])
        self.db.commit()

    def setdefault(self, key, value):
        key = key.lower()
        value = json.dumps(value)
        try :
            self.c.execute("insert into state (key, value) VALUES (?,?)", [key, value])
            return True
        except sqlite3.IntegrityError:
            return False

    def items(self):
        self.c.execute("select key, value from state")
        return [(k, json.loads(v)) for (k,v) in self.c.fetchall()]
