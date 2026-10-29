from three_mm_application_sdk import ApplicationMigration

def first(db):
    db.execute('CREATE TABLE value_state (id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL)')
    db.execute('INSERT INTO value_state VALUES (1,0)')
    db.execute('CREATE TABLE requests (request_key TEXT PRIMARY KEY, amount INTEGER NOT NULL, result_json TEXT NOT NULL)')

def get_migrations():
    return [ApplicationMigration('0001',first)]
