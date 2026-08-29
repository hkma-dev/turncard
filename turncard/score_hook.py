"""Hook 2 of 2 - Stop.

Grades the answer that just finished and records its faults, so hook 1 can put
them on the next card.

The Stop hook receives the finished reply as `last_assistant_message`, so this
script never has to parse a transcript file.

Default mode is "feedforward": always exit 0, never block. In "strict" mode this
hook sends a reply that scores below the threshold back for one rewrite, at most
once per turn, so it cannot loop.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    message = payload.get("last_assistant_message") or ""

    result = engine.score_text(message, config)
    state = engine.read_state(session_id)
    retention = config.get("state_retention_days", 7)

    # A short reply carries too little prose to judge. Keep the previous
    # feedback rather than wiping it with a meaningless perfect score.
    if result.get("skipped"):
        state["turns_skipped"] = state.get("turns_skipped", 0) + 1
        engine.write_state(session_id, state, retention)
        return 0

    history = state.get("history") or []
    history.append(result["score"])
    state["history"] = history[-50:]
    state["last"] = {
        "score": result["score"],
        "grade": result["grade"],
        "counts": result["counts"],
        "slips": result["slips"],
    }

    threshold = config.get("strict_block_below", 70)
    strict = config.get("mode") == "strict"

    # Never ask for a second rewrite of the same turn. Two independent guards,
    # because a payload may carry either field and an absent field must not
    # read as "already retried":
    #   stop_hook_active - Claude Code sets it when this Stop follows a block
    #   retried_turn     - our own marker, keyed on the reply we asked about
    turn_key = payload.get("prompt_id") or result["score"]
    already_retried = (
        bool(payload.get("stop_hook_active"))
        or (state.get("retried_turn") is not None
            and state.get("retried_turn") == turn_key)
    )

    if strict and result["score"] < threshold and not already_retried:
        state["retried_turn"] = turn_key
        engine.write_state(session_id, state, retention)
        reason = (
            "That reply scored %d/100 against the card, below the %d needed. "
            "Rewrite the prose of your last reply to meet the card, and send "
            "only the rewritten reply. Fix these:\n%s"
            % (
                result["score"],
                threshold,
                "\n".join("- %s" % s for s in result["slips"][:8]),
            )
        )
        # The Stop event reads a top-level decision. permissionDecision belongs
        # to PreToolUse and Claude Code ignores it here.
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0

    state.pop("retried_turn", None)
    engine.write_state(session_id, state, retention)

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
