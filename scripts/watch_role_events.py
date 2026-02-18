#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: watch_role_events.py <role>", file=sys.stderr)
        return 1

    role = sys.argv[1]

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue

        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue

        payload = item.get("payload", {})
        event = item.get("event", "")
        ts = item.get("timestamp", "")

        roles = payload.get("roles", [])
        moderator = payload.get("moderator")
        payload_role = payload.get("role")

        is_match = (
            payload_role == role
            or moderator == role
            or (isinstance(roles, list) and role in roles)
        )

        if is_match:
            print(f"[{ts}] {event} {payload}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
