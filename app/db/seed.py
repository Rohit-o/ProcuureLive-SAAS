from app.db.database import get_connection

def is_seeded():
    """
    Check if vendors table already has data.
    If yes, we do not seed again.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as count FROM vendors")
    row = cur.fetchone()

    conn.close()

    return row["count"] > 0


def seed_demo_data():
    """
    Insert demo data into tables.
    """
    conn = get_connection()
    cur = conn.cursor()

    print("Seeding demo data...")

    # ---------------------------
    # Insert Raw Materials
    # ---------------------------
    rms = [
        ("Paracetamol API", "IP Grade, Assay ≥ 99%", "High"),
        ("Microcrystalline Cellulose (MCC)", "PH102 Grade", "Medium"),
    ]

    cur.executemany(
        "INSERT INTO rm_master (rm_name, spec_short, criticality) VALUES (?, ?, ?)",
        rms
    )

    # ---------------------------
    # Insert Vendors 
    # ---------------------------
    vendors = [
        ("HealthyChem Pharma Pvt Ltd", 1, "Low"),
        ("BudgetBulk Chemicals", 1, "Medium"),
        ("FastDeal Traders", 1, "High"),
    ]

    cur.executemany(
        "INSERT INTO vendors (vendor_name, approved, risk_rating) VALUES (?, ?, ?)",
        vendors
    )

    # ---------------------------
    # Insert 1 PR (Requirement)
    # ---------------------------
    # Get rm_id for Paracetamol API
    cur.execute("SELECT rm_id FROM rm_master WHERE rm_name = ?", ("Paracetamol API",))
    rm_row = cur.fetchone()
    paracetamol_rm_id = rm_row["rm_id"]

    # Create PR
    cur.execute(
        """
        INSERT INTO pr (rm_id, qty, need_by, site, created_by, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (paracetamol_rm_id, 1000.0, "2026-03-10", "Formulation-Unit-1", "Purchase", "Open")
    )
    pr_id = cur.lastrowid

    # ---------------------------
    # Insert 1 RFQ for this PR
    # ---------------------------
    cur.execute(
        "INSERT INTO rfq (pr_id, status) VALUES (?, ?)",
        (pr_id, "Open")
    )
    rfq_id = cur.lastrowid

    # ---------------------------
    # Insert Quotes (3 vendors)
    # ---------------------------
    # Fetch vendor IDs
    cur.execute("SELECT vendor_id, vendor_name FROM vendors")
    vendor_rows = cur.fetchall()
    vmap = {row["vendor_name"]: row["vendor_id"] for row in vendor_rows}

    quotes = [
        (rfq_id, vmap["HealthyChem Pharma Pvt Ltd"], 520.0, 12, "30 days credit", 10, "Reliable GMP, best quality"),
        (rfq_id, vmap["BudgetBulk Chemicals"],       495.0, 18, "Advance",        7,  "Cheapest but slower lead time"),
        (rfq_id, vmap["FastDeal Traders"],           480.0, 15, "Advance",        7,  "Low price; risk/quality concerns"),
    ]

    cur.executemany(
        """
        INSERT INTO quotes (rfq_id, vendor_id, price, lead_time_days, payment_terms, validity_days, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        quotes
    )


    conn.commit()
    conn.close()

    print("Demo data seeded successfully.")