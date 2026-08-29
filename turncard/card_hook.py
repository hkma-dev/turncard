"""Hook 1 of 2 - UserPromptSubmit.

Adds the rulepack card to every prompt, with the faults found in the last answer.
Claude Code adds this script's stdout to the model's context for this turn.

This hook never blocks a prompt. If anything fails, it prints nothing and
exits 0, so a broken card can never break the session.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    session_id = payload.get("session_id", "unknown")

    card = engine.load_card(config)
    state = engine.read_state(session_id)

    lines = ["<turncard>", card, ""]

    last = state.get("last") or {}
    history = state.get("history") or []

    if not last:
        lines.append("LAST: no score yet.")
    else:
        average = round(sum(history) / len(history)) if history else last.get("score", 0)
        lines.append("LAST: %s/100 %s. Avg %s over %d."
                     % (last.get("score", "?"), last.get("grade", "?"),
                        average, len(history)))
        slips = last.get("slips") or []
        if slips:
            limit = config.get("max_slips_on_card", 5)
            lines.append("FIX:")
            for slip in slips[:limit]:
                lines.append("  - %s" % slip)
            extra = len(slips) - limit
            if extra > 0:
                lines.append("  - +%d more of the same." % extra)
        else:
            lines.append("Clean. Hold it.")

    # Narrow instruction: stop the model narrating "per the card..." in every
    # answer. It must not read as a blanket order to hide turncard from you, so
    # it says what to skip, not what to conceal. The README documents this line.
    lines.append("Apply this silently. Do not narrate the card in your reply.")
    lines.append("</turncard>")

    print("\n".join(lines))


try:
    main()
except Exception:
    pass
sys.exit(0)
