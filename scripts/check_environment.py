#!/usr/bin/env python3
import importlib
import platform
import sys

MODULES = ("fastapi", "sqlalchemy", "alembic", "pydantic_settings", "httpx", "moomoo")


def main() -> int:
    print(f"Python: {platform.python_version()}")
    baseline_ok = sys.version_info[:2] == (3, 9)
    print(f"Python 3.9基线：{'通过' if baseline_ok else '不通过'}")
    missing = []
    for module in MODULES:
        try:
            importlib.import_module(module)
            print(f"{module}：已安装")
        except ImportError:
            missing.append(module)
            print(f"{module}：缺失")
    return 1 if missing or not baseline_ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
