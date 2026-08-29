"""Claude Code adapter, hook 1 of 2. Event: UserPromptSubmit.

Deals this turn's card. Claude Code adds this script's stdout to the model's
context, so the card goes out as plain text.

This hook never blocks a prompt. On any error it prints nothing and exits 0, so
a broken card cannot break your session.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "turncard"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    import engine

    config = engine.load_config()
    if not config.get("enabled", True):
        return

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    print(engine.build_card(payload.get("session_id", "unknown"), config))


try:
    main()
except Exception:
    pass
sys.exit(0)
