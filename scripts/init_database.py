#!/usr/bin/env python3
from app.core.config import get_settings
from app.database.init import create_schema, seed_default_portfolios
from app.database.session import get_engine, get_session_factory


def main() -> None:
    settings = get_settings()
    engine = get_engine()
    create_schema(engine)
    with get_session_factory()() as db:
        seed_default_portfolios(db, settings)
    print("Database initialized with AGGRESSIVE, BALANCED, CONSERVATIVE portfolios.")


if __name__ == "__main__":
    main()
