"""Create the first independent admin account.

Usage: python -m app.commands.create_admin --email admin@example.com
"""
from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password, validate_password_strength
from app.models import Admin


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--password")
    args = p.parse_args()
    password = args.password or getpass.getpass("Admin password: ")
    problem = validate_password_strength(password)
    if problem:
        p.error(problem)
    with SessionLocal() as db:
        email = args.email.strip().lower()
        if db.scalar(select(Admin).where(Admin.email == email)):
            p.error("An admin with this email already exists")
        db.add(Admin(email=email, password_hash=hash_password(password)))
        db.commit()
    print(f"Created admin {email}")


if __name__ == "__main__":
    main()
