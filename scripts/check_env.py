#!/usr/bin/env python3
"""Aniz pre-flight checks. Exits 0 only when every required subsystem passes."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


def load_values(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values
    values = {key: str(value) for key, value in dotenv_values(path).items() if value is not None}
    values.update({key: value for key, value in os.environ.items() if key in values or key in REQUIRED_CLOUD | REQUIRED_PC})
    return values


REQUIRED_CLOUD = {"MONGODB_URI", "DATABASE_NAME", "ADMIN_PASSWORD", "ADMIN_SESSION_SECRET"}
REQUIRED_PC = {"MONGODB_URI", "DATABASE_NAME", "API_ID", "API_HASH", "STRING_SESSION", "TG_CHANNEL_ID", "BOT_TOKEN", "ADMIN_USER_IDS", "ARIA2_HOST", "ARIA2_PORT", "ARIA2_SECRET", "CONVERT_MKV_TO_MP4", "NYAA_FEED_URLS", "NYAA_CHECK_INTERVAL_MINUTES", "QUALITY_FILTERS", "RELEASE_GROUPS"}


def validate_config(values: dict[str, str]) -> tuple[bool, str]:
    role = values.get("DEPLOYMENT_ROLE", "pc").lower()
    required = REQUIRED_CLOUD if role == "cloud" else REQUIRED_PC
    missing = sorted(key for key in required if not values.get(key))
    placeholders = sorted(key for key in required if "replace-me" in values.get(key, "").lower())
    if missing:
        return False, f"missing: {', '.join(missing)}"
    if placeholders:
        return False, f"placeholder values: {', '.join(placeholders)}"
    try:
        if role == "pc" and (int(values["API_ID"]) <= 0 or int(values["TG_CHANNEL_ID"]) == 0):
            raise ValueError("Telegram IDs are invalid")
        for key in (("ARIA2_PORT", "NYAA_CHECK_INTERVAL_MINUTES") if role == "pc" else ()):
            if int(values[key]) <= 0:
                raise ValueError(f"{key} must be positive")
        if role == "pc":
            qualities = json.loads(values["QUALITY_FILTERS"])
            groups = json.loads(values["RELEASE_GROUPS"])
            if not isinstance(qualities, list) or not all(isinstance(x, str) and x for x in qualities):
                raise ValueError("QUALITY_FILTERS must be a JSON string array")
            if not isinstance(groups, list) or not all(isinstance(x, str) and x for x in groups):
                raise ValueError("RELEASE_GROUPS must be a JSON string array")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return False, str(exc)
    return True, "configuration parsed"


def check_mongodb(values: dict[str, str]) -> tuple[bool, str]:
    from pymongo import MongoClient
    try:
        client = MongoClient(values["MONGODB_URI"], serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        client.close()
        return True, "ping succeeded"
    except Exception as exc:  # noqa: BLE001 - diagnostic boundary
        return False, str(exc).splitlines()[0][:160]


def check_aria2(values: dict[str, str]) -> tuple[bool, str]:
    import aria2p
    try:
        client = aria2p.Client(host=f"http://{values['ARIA2_HOST']}", port=int(values["ARIA2_PORT"]), secret=values["ARIA2_SECRET"], timeout=3)
        version = aria2p.API(client).get_version()
        return True, f"aria2 {version.version}"
    except Exception as exc:  # noqa: BLE001 - diagnostic boundary
        return False, str(exc).splitlines()[0][:160]


async def check_telegram(values: dict[str, str]) -> tuple[bool, str]:
    from pyrogram import Client
    try:
        client = Client("aniz-preflight", api_id=int(values["API_ID"]), api_hash=values["API_HASH"], session_string=values["STRING_SESSION"], in_memory=True)
        async with client:
            me = await client.get_me()
            return True, f"authenticated as @{me.username or me.first_name}"
    except Exception as exc:  # noqa: BLE001 - diagnostic boundary
        return False, str(exc).splitlines()[0][:160]


async def run(path: Path) -> int:
    results: list[tuple[str, bool, str]] = []
    values = load_values(path)
    ok, detail = validate_config(values)
    results.append(("Configuration", ok, detail))
    role = values.get("DEPLOYMENT_ROLE", "pc").lower()
    if ok and role == "pc":
        results.append(("MongoDB", *check_mongodb(values)))
        results.append(("aria2 RPC", *check_aria2(values)))
        results.append(("Telegram MTProto", *(await check_telegram(values))))
    elif ok:
        results.append(("MongoDB", *check_mongodb(values)))
        results.append(("aria2 RPC", True, "skipped for cloud role"))
        results.append(("Telegram MTProto", True, "skipped for cloud role"))
    else:
        results.extend([(name, False, "skipped because configuration failed") for name in ("MongoDB", "aria2 RPC", "Telegram MTProto")])
    print("\nAniz pre-flight diagnostics")
    print("=" * 78)
    print(f"{'Subsystem':<22} {'Status':<10} Details")
    print("-" * 78)
    for name, passed, detail in results:
        print(f"{name:<22} {'[SUCCESS]' if passed else '[FAILED]':<10} {detail}")
    print("=" * 78)
    return 0 if all(passed for _, passed, _ in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    if not args.env_file.exists():
        print(f"[FAILED] env file not found: {args.env_file}", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(asyncio.run(run(args.env_file)))


if __name__ == "__main__":
    main()
