#!/usr/bin/env python3
import importlib
import platform
import sys

MODULES = ("fastapi", "sqlalchemy", "alembic", "pydantic_settings", "httpx")


def main() -> int:
    print(f"Python: {platform.python_version()}")
    print(f"Python target 3.12: {'YES' if sys.version_info >= (3, 12) else 'NO (3.9+ compatible dev mode)'}")
    missing = []
    for module in MODULES:
        try:
            importlib.import_module(module)
            print(f"{module}: OK")
        except ImportError:
            missing.append(module)
            print(f"{module}: MISSING")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
