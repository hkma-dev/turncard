"""Gemini CLI adapter, hook 2 of 2. Event: AfterAgent.

AfterAgent "fires once per turn after the model generates its final response",
and hands over the answer as `prompt_response`. Use AfterAgent, never AfterModel,
because AfterModel fires for every streaming chunk.

Gemini cannot annotate an answer. Its only levers are accept, reject and retry,
halt, and a `systemMessage` line shown to you. So feedforward mode accepts and
records, and strict mode denies with a reason, which Gemini sends to the agent
as a new prompt.

`stop_hook_active` marks a run that is already part of a retry, so strict mode
checks it and cannot loop.

STDOUT MUST HOLD THE JSON AND NOTHING ELSE.

UNTESTED. Written against Gemini CLI's published hook reference, not against a
running Gemini CLI.
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
        print("{}")
        return

    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("{}")
        return

    session_id = payload.get("session_id", "unknown")
    result = engine.record_answer(session_id, payload.get("prompt_response"), config)
    if result is None:
        print("{}")
        return

    if (config.get("mode") == "strict"
            and result["score"] < config.get("strict_block_below", 70)
            and not payload.get("stop_hook_active")):
        print(json.dumps({"decision": "deny",
                          "reason": engine.rewrite_request(result, config)}))
        return

    show = config.get("show_score", "on_slip")
    if show == "always" or (show == "on_slip" and result["grade"] != "PASS"):
        top = result["slips"][0] if result["slips"] else ""
        print(json.dumps({
            "systemMessage": "STE %d/100 (%s)%s"
            % (result["score"], result["grade"], " - " + top if top else ""),
        }))
        return

    print("{}")


try:
    main()
except Exception:
    try:
        print("{}")
    except Exception:
        pass
sys.exit(0)
