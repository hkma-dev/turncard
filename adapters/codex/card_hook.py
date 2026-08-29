"""Codex CLI adapter, hook 1 of 2. Event: UserPromptSubmit.

Codex does NOT add plain stdout to the model context. It reads one JSON object
and takes the card from hookSpecificOutput.additionalContext, which Codex adds
as extra developer context for this turn.

Input fields Codex sends on stdin: cwd, hook_event_name, model, permission_mode,
prompt, session_id, transcript_path, turn_id.

UNTESTED. Written against Codex's published hook schemas, not against a running
Codex. Report anything that misbehaves.
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
            "hookEventName": "UserPromptSubmit",
            "additionalContext": card,
        }
    }))


try:
    main()
except Exception:
    pass
sys.exit(0)
