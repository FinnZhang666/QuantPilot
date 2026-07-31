"""Audit the configured database against the Git ORM metadata without writes."""

import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import get_settings
from app.database.base import Base
from app.database import models  # noqa: F401


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    database_tables = set(inspector.get_table_names())
    application_tables = database_tables - {"alembic_version"}
    metadata_tables = set(Base.metadata.tables)
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    column_mismatches = []
    for table in sorted(application_tables & metadata_tables):
        actual = {column["name"] for column in inspector.get_columns(table)}
        expected = {column.name for column in Base.metadata.tables[table].columns}
        if actual != expected:
            column_mismatches.append({
                "table": table,
                "missing": sorted(expected - actual),
                "extra": sorted(actual - expected),
            })

    print("Revision:", revision)
    print("Tables (%d):" % len(application_tables))
    for table in sorted(application_tables):
        print("-", table)
    print("Missing tables:", sorted(metadata_tables - application_tables))
    print("Extra tables:", sorted(application_tables - metadata_tables))
    print("Column mismatches:", column_mismatches)
    return int(
        revision != "0019"
        or application_tables != metadata_tables
        or bool(column_mismatches)
    )


if __name__ == "__main__":
    raise SystemExit(main())
