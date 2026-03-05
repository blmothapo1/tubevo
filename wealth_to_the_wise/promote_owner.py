#!/usr/bin/env python3
"""
One-off: Promote the owner account to admin + agency plan.
Run with: railway run -- python promote_owner.py
"""
import os, sys

def main():
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        print("ERROR: DATABASE_URL not set. Run via `railway run`.")
        sys.exit(1)
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql://", 1)
    if "+asyncpg" in raw:
        raw = raw.replace("+asyncpg", "")

    from sqlalchemy import create_engine, text
    engine = create_engine(raw)

    with engine.begin() as conn:
        # Find all users
        rows = conn.execute(text(
            "SELECT id, email, role, plan, credit_balance FROM users"
        )).fetchall()

        if not rows:
            print("No users found!")
            return

        print(f"Found {len(rows)} user(s):")
        for r in rows:
            print(f"  {r[1]}  role={r[2]}  plan={r[3]}  credits={r[4]}")

        # Promote the first user (you) to admin + agency
        user_id = rows[0][0]
        email = rows[0][1]

        conn.execute(text(
            "UPDATE users SET role = 'admin', plan = 'agency', credit_balance = 999999 WHERE id = :uid"
        ), {"uid": user_id})

        print(f"\n✅ Promoted {email}:")
        print(f"   role    → admin")
        print(f"   plan    → agency (999,999 videos/month)")
        print(f"   credits → 999,999")

    engine.dispose()
    print("\n🎉 You now have full unlimited access. Log out and log back in to refresh your session.")

if __name__ == "__main__":
    main()
