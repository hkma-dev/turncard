"""Gemini CLI adapter, hook 1 of 2. Event: BeforeAgent.

BeforeAgent "fires after a user submits a prompt, but before the agent begins
planning", and hookSpecificOutput.additionalContext is "appended to the prompt
for this turn only". That is exactly what the card needs.

STDOUT MUST HOLD THE JSON AND NOTHING ELSE. Gemini's docs are blunt about this:
a single stray print breaks parsing. So this script prints once, or not at all.

UNTESTED. Written against Gemini CLI's published hook reference, not against a
running Gemini CLI.
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
        return

    card = engine.build_card(payload.get("session_id", "unknown"), config)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "BeforeAgent",
            "additionalContext": card,
        }
    }))


try:
    main()
except Exception:
    pass
sys.exit(0)
