import json
import sqlite3

from ZeekControl.exceptions import RuntimeEnvironmentError

class SqliteState:
    def __init__(self, path):
        self.path = path

        try:
            self.db = sqlite3.connect(self.path)
        except sqlite3.Error as err:
            raise RuntimeEnvironmentError("%s: %s\nCheck if the user running ZeekControl has both write and search permission to\nthe directory containing the database file and has both read and write\npermission to the database file itself." % (err, path))

        self.c = self.db.cursor()

        try:
            self.setup()
        except sqlite3.Error as err:
            raise RuntimeEnvironmentError("%s: %s\nCheck if the user running ZeekControl has write access to the database file.\nOtherwise, the database file is possibly corrupt." % (err, path))

    def setup(self):
        # Create table
        self.c.execute('''CREATE TABLE IF NOT EXISTS state (
            key   TEXT  PRIMARY KEY  NOT NULL,
            value TEXT
        )''')

        self.db.commit()

    def get(self, key):
        self.c.execute("SELECT value FROM state WHERE key=?", [key])
        records = self.c.fetchall()
        if records:
            return json.loads(records[0][0])
        return None

    def set(self, key, value):
        value = json.dumps(value)
        try:
            self.c.execute("REPLACE INTO state (key, value) VALUES (?,?)", [key, value])
        except sqlite3.Error as err:
            raise RuntimeEnvironmentError("%s: %s\nCheck if the user running ZeekControl has write access to the database file." % (err, self.path))

        self.db.commit()

    def items(self):
        self.c.execute("SELECT key, value FROM state")
        return [(k, json.loads(v)) for (k, v) in self.c.fetchall()]
