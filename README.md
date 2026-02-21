## ProcureLive SaaS (Prototype)
Real-time procurement governance: system recommendation vs purchase decision (with audit trail).

---

## Quick Start (Fresh Machine)

### 1) Setup Python environment
```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

### Important Note About Database

- The SQLite database file (`data/procurement.db`) is **not tracked in Git**.
- Each machine (local laptop, Codespaces, etc.) maintains its own local database file.
- If you clone the repository on a new machine, you must initialize the database using:

```bash
python -m app.test_db
python -m app.seed