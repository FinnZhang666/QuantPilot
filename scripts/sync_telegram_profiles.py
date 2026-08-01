#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.telegram_runtime.runtime import get_telegram_runtime


def parser():
    value = argparse.ArgumentParser(description="Sync Trade Companion Telegram Bot profiles")
    target = value.add_mutually_exclusive_group(required=True)
    target.add_argument("--bot", help="Bot registry alias")
    target.add_argument("--all", action="store_true", help="Process every Bot profile")
    value.add_argument(
        "--apply", action="store_true",
        help="Call the Telegram API; the default is a network-free dry run",
    )
    return value


def main():
    args = parser().parse_args()
    runtime = get_telegram_runtime(get_settings())
    try:
        result = runtime.sync_profiles(
            dry_run=not args.apply, alias=None if args.all else args.bot,
        )
    except ValueError:
        print(json.dumps({"status": "FAILED", "message": "Unknown Bot alias."}))
        return 2
    result["network_requested"] = bool(args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
