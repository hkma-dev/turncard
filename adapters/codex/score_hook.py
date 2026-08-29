"""Codex CLI adapter, hook 2 of 2. Event: Stop.

Codex hands the finished answer over as `last_assistant_message`, the same field
name Claude Code uses, so this adapter is close to its Claude Code twin.

Input fields Codex sends on stdin: cwd, hook_event_name, last_assistant_message,
model, permission_mode, session_id, stop_hook_active, transcript_path, turn_id.
`last_assistant_message` is nullable, so treat a null as nothing to grade.

UNTESTED. Written against Codex's published hook schemas, not against a running
Codex. Strict mode here is the least certain part, because Codex documents the
Stop input schema more clearly than the Stop output shape.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "turncard"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    import engine

    config = engine.load_config()
    if not config.get("enabled", True):
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    session_id = payload.get("session_id", "unknown")
    result = engine.record_answer(session_id, payload.get("last_assistant_message"), config)
    if result is None:
        return 0

    if config.get("mode") == "strict" and result["score"] < config.get("strict_block_below", 70):
        # stop_hook_active tells us this Stop follows a block we already made.
        if not payload.get("stop_hook_active"):
            print(json.dumps({"decision": "block",
                              "reason": engine.rewrite_request(result, config)}))
            return 0

    show = config.get("show_score", "on_slip")
    if show == "always" or (show == "on_slip" and result["grade"] != "PASS"):
        top = result["slips"][0] if result["slips"] else ""
        print(json.dumps({
            "systemMessage": "STE %d/100 (%s)%s"
            % (result["score"], result["grade"], " - " + top if top else ""),
            "suppressOutput": True,
        }))
    return 0


try:
    code = main()
except Exception:
    code = 0
sys.exit(code or 0)
