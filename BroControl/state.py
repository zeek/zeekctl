import json
import sqlite3

class SqliteState:
    def __init__(self, path):
        self.path = path

        try:
            self.db = sqlite3.connect(self.path)
        except sqlite3.Error as err:
            raise sqlite3.Error("%s: %s\nCheck if the user running BroControl has both write and search permission to\nthe directory containing the database file and has both read and write\npermission to the database file itself." % (err, path))

        self.c = self.db.cursor()

        try:
            self.setup()
        except sqlite3.Error as err:
            raise sqlite3.Error("%s: %s" % (err, path))

    def setup(self):
        # Create table
        self.c.execute('''CREATE TABLE IF NOT EXISTS state (
            key   TEXT  PRIMARY KEY  NOT NULL,
            value TEXT
        )''')

        self.db.commit()

    def get(self, key):
        key = key.lower()
        self.c.execute("SELECT value FROM state WHERE key=?", [key])
        records = self.c.fetchall()
        if records:
            return json.loads(records[0][0])
        return None

    def set(self, key, value):
        key = key.lower()
        value = json.dumps(value)
        try:
            self.c.execute("REPLACE INTO state (key, value) VALUES (?,?)", [key, value])
        except sqlite3.Error as err:
            raise sqlite3.Error("%s: %s" % (err, self.path))

        self.db.commit()

    def items(self):
        self.c.execute("SELECT key, value FROM state")
        return [(k, json.loads(v)) for (k, v) in self.c.fetchall()]
