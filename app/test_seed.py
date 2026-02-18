from app.db.schema import create_tables
from app.db.seed import is_seeded, seed_demo_data

if __name__ == "__main__":
    create_tables()

    if not is_seeded():
        seed_demo_data()
        print("Seeding done.")
    else:
        print("Already seeded.")