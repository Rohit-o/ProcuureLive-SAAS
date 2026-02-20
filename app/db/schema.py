from app.db.database import get_connection

def create_tables():
    """
    Creates all required tables if they don't already exist.
    Run this once at app startup.
    """
    conn = get_connection()
    cur = conn.cursor()

    # 1) Raw Material master
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rm_master (
        rm_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rm_name TEXT NOT NULL,
        spec_short TEXT,
        criticality TEXT CHECK(criticality IN ('Low','Medium','High')) DEFAULT 'Medium'
    )
    """)

    # 2) Vendor master
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vendors (
        vendor_id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_name TEXT NOT NULL,
        approved INTEGER DEFAULT 0, -- 0 = No, 1 = Yes
        risk_rating TEXT CHECK(risk_rating IN ('Low','Medium','High')) DEFAULT 'Medium'
    )
    """)

    # 3) Purchase Requirement (PR) - internal demand
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pr (
        pr_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rm_id INTEGER NOT NULL,
        qty REAL NOT NULL,
        need_by TEXT NOT NULL,         -- store as YYYY-MM-DD
        site TEXT,
        created_by TEXT,
        status TEXT DEFAULT 'Open',
        created_on TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (rm_id) REFERENCES rm_master(rm_id)
    )
    """)

    # 4) RFQ - a request for quotations for a PR
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rfq (
        rfq_id INTEGER PRIMARY KEY AUTOINCREMENT,
        pr_id INTEGER NOT NULL,
        status TEXT DEFAULT 'Open',
        created_on TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (pr_id) REFERENCES pr(pr_id)
    )
    """)

    # 5) Quotes - vendor responses for an RFQ
    cur.execute("""
    CREATE TABLE IF NOT EXISTS quotes (
        quote_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rfq_id INTEGER NOT NULL,
        vendor_id INTEGER NOT NULL,
        price REAL NOT NULL,
        lead_time_days INTEGER NOT NULL,
        payment_terms TEXT,
        validity_days INTEGER,
        notes TEXT,
        created_on TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (rfq_id) REFERENCES rfq(rfq_id),
        FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id)
    )
    """)

        # 6) RFQ Decision - final selection made by purchase/approver
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rfq_decision (
        decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rfq_id INTEGER NOT NULL,
        selected_vendor_id INTEGER NOT NULL,
        selected_by TEXT NOT NULL,
        override_reason TEXT,
        created_on TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (rfq_id) REFERENCES rfq(rfq_id),
        FOREIGN KEY (selected_vendor_id) REFERENCES vendors(vendor_id),
        UNIQUE (rfq_id)
    )
    """)
        # 7) Recommendation snapshot (freeze system view at time of decision)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rfq_recommendation_snapshot (
        snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rfq_id INTEGER NOT NULL UNIQUE,
        recommended_vendor_id INTEGER NOT NULL,
        cheapest_vendor_id INTEGER NOT NULL,
        weights TEXT,  -- store something like "price=0.65,lead=0.35,high=-40,med=-15"
        created_on TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (rfq_id) REFERENCES rfq(rfq_id),
        FOREIGN KEY (recommended_vendor_id) REFERENCES vendors(vendor_id),
        FOREIGN KEY (cheapest_vendor_id) REFERENCES vendors(vendor_id)
    )
    """)

    conn.commit()
    conn.close()