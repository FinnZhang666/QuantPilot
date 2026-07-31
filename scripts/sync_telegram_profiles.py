#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.telegram_product.bot_profiles import load_bot_profiles
from app.telegram_product.profile_sync import TelegramProfileSynchronizer


def parser():
    value = argparse.ArgumentParser(description="同步 Trade Companion Telegram Bot 品牌资料")
    target = value.add_mutually_exclusive_group(required=True)
    target.add_argument("--bot", help="Bot 配置别名")
    target.add_argument("--all", action="store_true", help="处理全部 Bot 配置")
    value.add_argument(
        "--apply", action="store_true",
        help="执行真实 Telegram API 请求；默认仅 dry-run",
    )
    return value


def main():
    args = parser().parse_args()
    profiles = load_bot_profiles(get_settings())
    selected = profiles if args.all else [item for item in profiles if item.alias == args.bot]
    if not selected:
        print(json.dumps({"status": "FAILED", "message": "Bot Alias不存在。"}, ensure_ascii=False))
        return 2
    synchronizer = TelegramProfileSynchronizer()
    results = [synchronizer.sync(item, dry_run=not args.apply) for item in selected]
    print(json.dumps({"items": results, "network_requested": bool(args.apply)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
