"""Claude Code adapter, hook 2 of 2. Event: Stop.

Grades the answer that just finished and records its faults, so hook 1 can put
them on the next card. Claude Code hands the finished answer over as
`last_assistant_message`, so this script never parses a transcript file.

Default mode is "feedforward": always exit 0, never block. In "strict" mode this
hook sends a failing answer back for one rewrite, at most once per turn.
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
        state = engine.read_state(session_id)
        turn_key = payload.get("prompt_id") or result["score"]
        already = (bool(payload.get("stop_hook_active"))
                   or (state.get("retried_turn") is not None
                       and state.get("retried_turn") == turn_key))
        if not already:
            state["retried_turn"] = turn_key
            engine.write_state(session_id, state, config.get("state_retention_days", 7))
            # Stop reads a top-level decision. permissionDecision is PreToolUse
            # only, and Claude Code ignores it here.
            print(json.dumps({"decision": "block",
                              "reason": engine.rewrite_request(result, config)}))
            return 0

    state = engine.read_state(session_id)
    if state.pop("retried_turn", None) is not None:
        engine.write_state(session_id, state, config.get("state_retention_days", 7))

    # Show the score in the terminal so you can see the system work.
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
