import getpass
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.db import DatabaseNotConfiguredError, get_session_factory
from app.models import User, UserRole
from app.security import hash_password

_DEMO_PASSWORD = "MahiDemo-Only-2026!"


def create_manager() -> int:
    settings = get_settings()
    if settings.database_url is None:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    try:
        email = str(TypeAdapter(EmailStr).validate_python(input("Manager email: "))).strip().lower()
    except ValidationError:
        print("Enter a valid email address.", file=sys.stderr)
        return 2

    user_id = input("Manager User ID: ").strip().lower()
    if len(user_id) < 3 or len(user_id) > 50 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for c in user_id):
        print("User ID must be 3-50 characters: letters, numbers, dot, underscore, or hyphen.", file=sys.stderr)
        return 2
    display_name = input("Manager display name (optional): ").strip() or user_id
    password = getpass.getpass("Manager password (at least 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(display_name) < 2:
        print("Display name must contain at least 2 characters.", file=sys.stderr)
        return 2
    if len(password) < 12 or len(password) > 128:
        print("Password must contain between 12 and 128 characters.", file=sys.stderr)
        return 2
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        return 2

    try:
        db = get_session_factory()()
    except DatabaseNotConfiguredError:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    try:
        if db.scalar(select(User.id).where((User.email == email) | (User.user_id == user_id))) is not None:
            print("An account already uses that User ID or email.", file=sys.stderr)
            return 1
        db.add(
            User(
                user_id=user_id,
                email=email,
                display_name=display_name,
                password_hash=hash_password(password),
                role=UserRole.MANAGER.value,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    print(f"Manager account created for {user_id} ({email}).")
    return 0


def create_demo_accounts() -> int:
    settings = get_settings()
    if settings.app_env != "development":
        print("Demo accounts may only be created when APP_ENV=development.", file=sys.stderr)
        return 2
    if settings.database_url is None:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    accounts = (
        ("demo.manager", "demo.manager@example.com", "Demo Manager", UserRole.MANAGER.value),
        ("demo.staff", "demo.staff@example.com", "Demo Staff", UserRole.STAFF.value),
    )
    try:
        db = get_session_factory()()
    except DatabaseNotConfiguredError:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    try:
        accounts_to_create = []
        accounts_updated = []
        for user_id, email, display_name, role in accounts:
            existing_user_id = db.scalar(select(User).where(User.user_id == user_id))
            existing_email = db.scalar(select(User).where(User.email == email))
            if existing_user_id is None and existing_email is None:
                accounts_to_create.append((user_id, email, display_name, role))
                continue
            if (
                existing_user_id is not None
                and existing_email is None
                and existing_user_id.email == f"{user_id}@example.test"
                and existing_user_id.role == role
            ):
                existing_user_id.email = email
                accounts_updated.append(user_id)
                continue
            if (
                existing_user_id is not None
                and existing_email is not None
                and existing_user_id.id == existing_email.id
                and existing_user_id.role == role
            ):
                continue
            print(
                f"A demo account already uses {user_id} or {email}; no accounts were created.",
                file=sys.stderr,
            )
            return 1

        db.add_all(
            User(
                user_id=user_id,
                email=email,
                display_name=display_name,
                password_hash=hash_password(_DEMO_PASSWORD),
                role=role,
                is_active=True,
            )
            for user_id, email, display_name, role in accounts_to_create
        )
        if accounts_to_create or accounts_updated:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if not accounts_to_create:
        print("Development demo accounts already exist; passwords and account status were left unchanged.")
        if accounts_updated:
            print("Updated legacy demo email addresses to validator-compatible placeholders.")
        return 0

    print("Development demo accounts are ready. New accounts use the local-only demo password: MahiDemo-Only-2026!")
    created_user_ids = {account[0] for account in accounts_to_create}
    for user_id, _, _, role in accounts:
        if user_id in created_user_ids:
            print(f"{role.title()} | User ID: {user_id}")
    if accounts_updated:
        print(f"Updated legacy demo account email addresses: {', '.join(accounts_updated)}")
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "create-manager":
        return create_manager()
    if len(sys.argv) == 2 and sys.argv[1] == "create-demo-accounts":
        return create_demo_accounts()
    print("Usage: python -m app.cli {create-manager|create-demo-accounts}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
