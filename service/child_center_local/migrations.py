"""Fresh local profile. Existing commercial data requires an explicit import."""
from three_mm_application_sdk import ApplicationMigration


def first(db):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='registrations'").fetchone():
        raise ValueError("Legacy Child Center storage requires a reviewed import; do not reset it")
    db.execute("""CREATE TABLE local_registrations (
        registration_id TEXT PRIMARY KEY, status TEXT NOT NULL,
        guardian_name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT NOT NULL,
        consent_version TEXT NOT NULL, consented_at TEXT NOT NULL,
        search_text TEXT NOT NULL, created_at TEXT NOT NULL, receipt_hash TEXT)""")
    db.execute("""CREATE TABLE local_children (
        child_id TEXT PRIMARY KEY, registration_id TEXT NOT NULL REFERENCES local_registrations,
        display_name TEXT NOT NULL)""")
    db.execute("""CREATE TABLE local_bracelets (
        assignment_id TEXT PRIMARY KEY, child_id TEXT NOT NULL REFERENCES local_children,
        code TEXT NOT NULL, assigned_at TEXT NOT NULL, retired_at TEXT)""")
    db.execute("CREATE UNIQUE INDEX local_live_code ON local_bracelets(code) WHERE retired_at IS NULL")
    db.execute("CREATE UNIQUE INDEX local_live_child ON local_bracelets(child_id) WHERE retired_at IS NULL")
    db.execute("""CREATE TABLE local_visits (
        visit_id TEXT PRIMARY KEY, child_id TEXT NOT NULL REFERENCES local_children,
        state TEXT NOT NULL, entered_at TEXT NOT NULL, inside_since TEXT,
        accumulated_us INTEGER NOT NULL, last_transition_at TEXT NOT NULL, exited_at TEXT)""")
    db.execute("CREATE UNIQUE INDEX local_active_child ON local_visits(child_id) WHERE state='active'")
    db.execute("""CREATE TABLE local_requests (
        request_key TEXT PRIMARY KEY, operation_id TEXT NOT NULL,
        fingerprint TEXT NOT NULL, result_json TEXT NOT NULL)""")
    db.execute("""CREATE TABLE local_audit (
        audit_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL,
        actor TEXT NOT NULL, occurred_at TEXT NOT NULL)""")


def administration(db):
    db.execute('ALTER TABLE local_registrations ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')


def get_migrations():
    return [ApplicationMigration('local_0001', first), ApplicationMigration('local_0002', administration),
            ApplicationMigration('local_0003', stay_history), ApplicationMigration('local_0004', network_readers),
            ApplicationMigration('local_0005', interactive_commerce),
            ApplicationMigration('local_0006', family_commerce),
            ApplicationMigration('local_0007', presentation_settings)]


def stay_history(db):
    db.execute('''CREATE TABLE local_visit_events (
        sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
        visit_id TEXT NOT NULL REFERENCES local_visits, kind TEXT NOT NULL,
        occurred_at TEXT NOT NULL, phase TEXT NOT NULL, accumulated_us INTEGER NOT NULL)''')
    db.execute('CREATE INDEX local_visit_event_order ON local_visit_events(visit_id,sequence)')
    # Old pause/resume timestamps cannot be reconstructed from a cumulative value.
    # Preserve a clearly marked snapshot without inventing a complete timeline.
    db.execute('''INSERT INTO local_visit_events(event_id,visit_id,kind,occurred_at,phase,accumulated_us)
        SELECT 'event_' || lower(hex(randomblob(16))),visit_id,'snapshot',last_transition_at,
          CASE WHEN state='closed' THEN 'closed' WHEN inside_since IS NULL THEN 'paused' ELSE 'inside' END,
          accumulated_us FROM local_visits ORDER BY entered_at,visit_id''')


def network_readers(db):
    db.execute('''CREATE TABLE local_reader_settings(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        revision INTEGER NOT NULL,mode TEXT NOT NULL,effective_from TEXT NOT NULL,
        toggle_ids TEXT NOT NULL,entry_ids TEXT NOT NULL,exit_ids TEXT NOT NULL)''')
    db.execute("INSERT INTO local_reader_settings VALUES(1,1,'disabled','1970-01-01T00:00:00+00:00','[]','[]','[]')")
    db.execute('''CREATE TABLE local_reader_events(sequence INTEGER PRIMARY KEY,event_id TEXT NOT NULL UNIQUE,
        fingerprint TEXT NOT NULL,device_id TEXT NOT NULL,reader_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,processed_at TEXT NOT NULL,outcome TEXT NOT NULL,
        visit_id TEXT REFERENCES local_visits,child_id TEXT REFERENCES local_children,result_json TEXT NOT NULL)''')


def interactive_commerce(db):
    db.execute("ALTER TABLE local_children ADD COLUMN allowed_articles TEXT NOT NULL DEFAULT '[]'")
    db.execute('''CREATE TABLE local_commerce_settings(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        revision INTEGER NOT NULL,time_article_id INTEGER,unit TEXT NOT NULL,places TEXT NOT NULL,articles TEXT NOT NULL)''')
    db.execute("INSERT INTO local_commerce_settings VALUES(1,1,NULL,'hours','[]','[]')")
    db.execute('''CREATE TABLE local_commerce_parents(registration_id TEXT PRIMARY KEY REFERENCES local_registrations,
        client_id INTEGER NOT NULL,source_digest TEXT NOT NULL)''')
    db.execute('''CREATE TABLE local_commerce_accounts(visit_id TEXT PRIMARY KEY REFERENCES local_visits,
        place_id INTEGER NOT NULL,client_id INTEGER NOT NULL,identity TEXT NOT NULL UNIQUE,account_id INTEGER,
        state TEXT NOT NULL,observed_at TEXT,remote_state TEXT NOT NULL DEFAULT 'unknown',
        time_article_id INTEGER NOT NULL,unit TEXT NOT NULL,quantity TEXT,time_confirmed INTEGER NOT NULL DEFAULT 0)''')
    db.execute("CREATE UNIQUE INDEX local_allocated_place ON local_commerce_accounts(place_id) WHERE state!='closed'")
    db.execute('''CREATE TABLE local_commerce_commands(sequence INTEGER PRIMARY KEY,command_id TEXT NOT NULL UNIQUE,
        owner_key TEXT NOT NULL,visit_id TEXT REFERENCES local_visits,registration_id TEXT REFERENCES local_registrations,
        kind TEXT NOT NULL,state TEXT NOT NULL,parameters TEXT NOT NULL,baseline TEXT,acknowledged INTEGER NOT NULL DEFAULT 0,
        candidate_id INTEGER,created_at TEXT NOT NULL,error_code TEXT)''')
    db.execute("CREATE UNIQUE INDEX local_commerce_pending ON local_commerce_commands(owner_key) WHERE state IN ('prepared','uncertain')")
    db.execute("CREATE UNIQUE INDEX local_commerce_one_time ON local_commerce_commands(visit_id) WHERE kind='time' AND state!='cancelled'")
    db.execute('''CREATE TABLE local_commerce_quotes(quote_id TEXT PRIMARY KEY,visit_id TEXT NOT NULL REFERENCES local_visits,
        actor TEXT NOT NULL,fingerprint TEXT NOT NULL,amount TEXT NOT NULL,currency_id INTEGER NOT NULL,
        currency_code TEXT NOT NULL,methods TEXT NOT NULL,expires_at TEXT NOT NULL,used INTEGER NOT NULL DEFAULT 0)''')
    db.execute('''CREATE TABLE local_commerce_requests(request_key TEXT PRIMARY KEY,operation_id TEXT NOT NULL,
        fingerprint TEXT NOT NULL,result_json TEXT)''')
    db.execute('''CREATE TABLE local_consumption_consents(sequence INTEGER PRIMARY KEY,child_id TEXT NOT NULL REFERENCES local_children,
        actor TEXT NOT NULL,consented_at TEXT NOT NULL,articles TEXT NOT NULL)''')


def family_commerce(db):
    db.execute('ALTER TABLE local_commerce_settings ADD COLUMN default_place_id INTEGER')
    db.execute('ALTER TABLE local_commerce_settings ADD COLUMN guardian_category_id INTEGER')
    db.execute('DROP INDEX local_allocated_place')
    db.execute('''CREATE TABLE local_commerce_families(
        visit_id TEXT PRIMARY KEY REFERENCES local_visits,
        registration_id TEXT NOT NULL REFERENCES local_registrations,
        opening_error TEXT)''')
    db.execute('''CREATE TABLE local_commerce_members(
        visit_id TEXT PRIMARY KEY REFERENCES local_visits,
        family_visit_id TEXT NOT NULL REFERENCES local_commerce_families)''')
    db.execute('CREATE INDEX local_family_members ON local_commerce_members(family_visit_id)')
    # Existing accounts retain their exact identity and orders. Never merge remote
    # bills or retrospectively sell time during a migration.
    db.execute('''INSERT INTO local_commerce_families(visit_id,registration_id)
        SELECT a.visit_id,c.registration_id FROM local_commerce_accounts a
        JOIN local_visits v ON v.visit_id=a.visit_id JOIN local_children c ON c.child_id=v.child_id''')
    db.execute('INSERT INTO local_commerce_members SELECT visit_id,visit_id FROM local_commerce_families')
    # Unlinked active stays may join the one existing family bill, but ambiguous
    # older bills are kept separate for explicit operator review.
    active=db.execute('''SELECT v.visit_id,c.registration_id FROM local_visits v
        JOIN local_children c ON c.child_id=v.child_id WHERE v.state='active'
        AND NOT EXISTS(SELECT 1 FROM local_commerce_members m WHERE m.visit_id=v.visit_id)
        ORDER BY v.entered_at,v.visit_id''').fetchall()
    for visit in active:
        families=db.execute('''SELECT f.visit_id FROM local_commerce_families f
            LEFT JOIN local_commerce_accounts a ON a.visit_id=f.visit_id
            WHERE f.registration_id=? AND (a.state IS NULL OR a.state!='closed')''',(visit[1],)).fetchall()
        anchor=families[0][0] if len(families)==1 else visit[0]
        if anchor==visit[0]:
            db.execute('INSERT INTO local_commerce_families(visit_id,registration_id) VALUES(?,?)',(anchor,visit[1]))
        db.execute('INSERT INTO local_commerce_members VALUES(?,?)',(visit[0],anchor))


def presentation_settings(db):
    # Add only application-owned presentation state. Existing business tables
    # and their records, receipts and remote identities are not rewritten.
    db.execute('''CREATE TABLE local_ui_settings(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        revision INTEGER NOT NULL CHECK(revision>=1),
        debug_mode INTEGER NOT NULL CHECK(debug_mode IN (0,1)))''')
    db.execute('INSERT INTO local_ui_settings VALUES(1,1,0)')
