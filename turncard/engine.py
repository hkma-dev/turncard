"""turncard - the scoring engine.

This module is deterministic: it makes no model call and no network call, and
it checks the rules a machine can check reliably. The rest of the rules live
in the rulepack card, which the model reads every turn.

Two hooks use it:
  card_hook.py   (UserPromptSubmit) - deals the card for this turn
  score_hook.py  (Stop)             - scores the reply and records what slipped
"""

import json
import re
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent   # repository root
STATE_DIR = BASE / "state"
DEFAULT_RULEPACK = "rulepacks/ste"
MAX_SCORED_CHARS = 200_000

DEFAULT_CONFIG = {
    "enabled": True,
    "mode": "feedforward",
    "rulepack": DEFAULT_RULEPACK,
    "max_sentence_words": 25,
    "max_paragraph_sentences": 6,
    "min_words_to_score": 25,
    "max_slips_on_card": 5,
    "pass_score": 90,
    "weak_score": 70,
    "strict_block_below": 70,
    "state_retention_days": 7,
    "penalties": {
        "long_sentence": 3,
        "passive_voice": 4,
        "progressive_tense": 2,
        "word_choice": 2,
        "avoid_word": 1,
        "semicolon": 2,
        "long_paragraph": 2,
        "banned_word": 1,
    },
    "use_banned_list": False,
    "max_penalty_per_rule": 15,
}


def _read_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return fallback


def load_config():
    config = dict(DEFAULT_CONFIG)
    user = _read_json(BASE / "config.json", {})
    penalties = dict(DEFAULT_CONFIG["penalties"])
    penalties.update(user.get("penalties") or {})
    config.update({k: v for k, v in user.items() if k != "penalties"})
    config["penalties"] = penalties
    return config


def rulepack_file(config, suffix):
    """Resolve one file of the active rulepack, e.g. rulepacks/ste.md."""
    name = (config or {}).get("rulepack") or DEFAULT_RULEPACK
    return BASE / (name + suffix)


def load_card(config):
    """The rules the model reads every turn."""
    try:
        return rulepack_file(config, ".md").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def load_lexicon(config=None):
    data = _read_json(rulepack_file(config, ".lexicon.json"), {})
    return data.get("replace") or {}, data.get("avoid") or []


def load_banned(config=None):
    """An optional list of words to flag, with no replacement offered.

    Ships empty. A rulepack may add <rulepack>.banned.json holding
    {"banned": ["word", ...]} when a standard names words to avoid but its
    replacements cannot be redistributed. See tools/extract_ste_words.py.
    """
    data = _read_json(rulepack_file(config, ".banned.json"), {})
    return data.get("banned") or data.get("not_approved") or []


# --- text preparation ------------------------------------------------------

FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
OPEN_FENCE = re.compile(r"```.*\Z", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+|www\.\S+")
WIN_PATH = re.compile(r"[A-Za-z]:[\\/][^\s,;)]+")
# Two guards against catastrophic backtracking. Each segment class excludes
# "/", so one position has one parse. Each segment is also length-bounded, so a
# long run of "-~" or "-." costs a fixed amount per start instead of scanning
# to the end of the reply. Unbounded, 128k chars of "-~" cost 60 seconds.
UNIX_PATH = re.compile(r"(?<![\w.])[~./][\w.~-]{0,64}(?:/[\w.~-]{1,64})+")
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")


def strip_technical(text):
    """Remove the parts of a reply that STE explicitly exempts."""
    text = FENCE.sub(" ", text)
    text = OPEN_FENCE.sub(" ", text)  # a code block the reply never closed
    text = MD_LINK.sub(r"\1", text)
    text = INLINE_CODE.sub(" ", text)
    text = URL.sub(" ", text)
    text = WIN_PATH.sub(" ", text)
    text = UNIX_PATH.sub(" ", text)
    return text


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+")
LIST_MARKER = re.compile(r"^\s*(?:[-*+>]|\d+[.)])\s+")
HEADING = re.compile(r"^\s*#{1,6}\s+")
EMPHASIS = re.compile(r"\*\*|__|\*|_")


def clean_line(line):
    line = HEADING.sub("", line)
    line = LIST_MARKER.sub("", line)
    line = EMPHASIS.sub("", line)
    return line.strip()


def get_sentences(text):
    """Return prose sentences. Table rows and empty lines are dropped."""
    found = []
    for raw in text.split("\n"):
        line = clean_line(raw)
        if not line or line.startswith("|") or set(line) <= set("-=| "):
            continue
        for part in SENTENCE_SPLIT.split(line):
            part = part.strip().strip("*_ ")
            if part and WORD.search(part):
                found.append(part)
    return found


def unwrap(block):
    """Join hard-wrapped prose lines back into whole paragraphs.

    A chat reply carries no hard wrapping, but a file does. Without this, each
    wrapped line counts as its own sentence and a normal paragraph in a README
    reads as seven sentences. A list item, heading or table row keeps its own
    line, because those are separate items and not a wrap.
    """
    joined = []
    for raw in block.split("\n"):
        line = raw.strip()
        if not line:
            continue
        own_line = bool(LIST_MARKER.match(raw) or HEADING.match(raw)
                        or line.startswith("|"))
        if joined and not own_line:
            joined[-1] = joined[-1] + " " + line
        else:
            joined.append(line)
    return "\n".join(joined)


def word_count(sentence):
    return len(WORD.findall(sentence))


def snippet(text, limit=64):
    """Quote a fragment of the reply for the next turn's card.

    The card is trusted context. Angle brackets come out, so text the model
    merely quoted from an untrusted file or web page cannot forge the card's
    own delimiters or inject a tag on the following turn.
    """
    text = " ".join(text.split())
    text = text.replace("<", "(").replace(">", ")")
    return text if len(text) <= limit else text[: limit - 3] + "..."


# --- rule checks -----------------------------------------------------------

BE_VERBS = r"(?:is|are|was|were|am|be|been|being|gets|get|got)"
PARTICIPLE_EXCEPTIONS = {
    "speed", "need", "indeed", "exceed", "proceed", "succeed", "agreed",
    "embed", "seed", "feed", "deed", "freed", "greed", "breed", "steed",
    "misled", "bed", "red", "fed", "led", "sled", "shed", "wed",
}
IRREGULAR = (
    "done|made|given|taken|seen|shown|found|held|kept|left|put|sent|set|"
    "written|built|brought|caught|chosen|drawn|driven|known|meant|met|paid|"
    "said|sold|told|thought|understood|run|read|lost|won|hidden|broken|"
    "spoken|driven|forgotten|frozen|stolen|torn|worn|thrown|grown|drawn"
)
PASSIVE = re.compile(
    r"\b" + BE_VERBS + r"\b(?:\s+(?:not|also|only|already|now|then|\w+ly))?"
    r"\s+(?P<part>\w{3,}ed|" + IRREGULAR + r")\b",
    re.I,
)
PROGRESSIVE = re.compile(
    r"\b(?:is|are|was|were|am|be|been|being)\b"
    r"(?:\s+(?:not|also|only|still|\w+ly))?\s+(?P<part>\w{3,}ing)\b",
    re.I,
)


def _inflect(word, kind):
    if kind == "base":
        return word
    if kind == "s":
        if word.endswith(("s", "x", "z", "ch", "sh")):
            return word + "es"
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            return word[:-1] + "ies"
        return word + "s"
    if kind == "ed":
        if word.endswith("e"):
            return word + "d"
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            return word[:-1] + "ied"
        return word + "ed"
    if kind == "ing":
        if word.endswith("e") and not word.endswith(("ee", "ye", "oe")):
            return word[:-1] + "ing"
        return word + "ing"
    return word


def expand_replacements(replace_map):
    """Match the inflected forms too: utilize, utilizes, utilized, utilizing."""
    expanded = {}
    for base, better in replace_map.items():
        expanded.setdefault(base.lower(), better)
        skip = (" " in base or "." in base or base.endswith("ly")
                or len(base) < 4 or not base.isalpha())
        if skip:
            continue
        head, _, tail = better.partition(" ")
        for kind in ("s", "ed", "ing"):
            variant = _inflect(base.lower(), kind)
            fixed = _inflect(head, kind) + ((" " + tail) if tail else "")
            expanded.setdefault(variant, fixed)
    return expanded


def build_word_pattern(terms):
    if not terms:
        return None
    parts = []
    for term in sorted(terms, key=len, reverse=True):
        if not term.strip() or len(term) > 40:
            continue    # a key of only spaces emits adjacent \s+ groups
        # Collapse a run of spaces into ONE \s+, so no key can emit adjacent
        # quantifiers that backtrack against each other.
        escaped = re.sub(r"(?:\\ )+", lambda _m: r"\s+", re.escape(term))
        lead = r"\b" if term[0].isalnum() else ""
        trail = r"\b" if term[-1].isalnum() else ""
        parts.append(lead + escaped + trail)
    return re.compile("|".join(parts), re.I)


def score_text(text, config=None, lexicon=None):
    """Score one reply. Returns a dict with the score, grade and slips."""
    config = config or load_config()
    replace_map, avoid_list = lexicon if lexicon else load_lexicon(config)
    penalties = config["penalties"]
    cap = config.get("max_penalty_per_rule", 15)

    # Bound the work regardless of what a reply contains.
    prose = strip_technical((text or "")[:MAX_SCORED_CHARS])
    sentences = get_sentences(prose)
    total_words = sum(word_count(s) for s in sentences)

    if total_words < config.get("min_words_to_score", 25):
        return {"skipped": True, "words": total_words}

    slips = []          # (rule, message, penalty)
    limit = config.get("max_sentence_words", 25)

    for sentence in sentences:
        count = word_count(sentence)
        if count > limit:
            slips.append((
                "long_sentence",
                "%d-word sentence: \"%s\"" % (count, snippet(sentence, 44)),
                penalties["long_sentence"],
            ))

        for match in PASSIVE.finditer(sentence):
            if match.group("part").lower() in PARTICIPLE_EXCEPTIONS:
                continue
            slips.append((
                "passive_voice",
                "Passive: \"%s\"" % snippet(match.group(0), 36),
                penalties["passive_voice"],
            ))

        for match in PROGRESSIVE.finditer(sentence):
            slips.append((
                "progressive_tense",
                "Progressive: \"%s\"" % snippet(match.group(0), 36),
                penalties["progressive_tense"],
            ))

        if ";" in sentence:
            slips.append((
                "semicolon",
                "Semicolon: \"%s\"" % snippet(sentence, 40),
                penalties["semicolon"],
            ))

    replace_map = expand_replacements(replace_map)
    replace_pattern = build_word_pattern(list(replace_map))
    if replace_pattern:
        seen = set()
        for match in replace_pattern.finditer(prose):
            found = " ".join(match.group(0).split())
            key = found.lower()
            if key in seen:
                continue
            seen.add(key)
            better = replace_map.get(key) or replace_map.get(found) or "a simpler word"
            slips.append((
                "word_choice",
                "\"%s\" -> \"%s\"" % (found, better),
                penalties["word_choice"],
            ))

    avoid_pattern = build_word_pattern(avoid_list)
    if avoid_pattern:
        seen = set()
        for match in avoid_pattern.finditer(prose):
            found = " ".join(match.group(0).split())
            key = found.lower()
            if key in seen:
                continue
            seen.add(key)
            slips.append((
                "avoid_word",
                "Cut: \"%s\"" % found,
                penalties["avoid_word"],
            ))

    if config.get("use_banned_list", False):
        already = set(replace_map) | {w.lower() for w in avoid_list}
        terms = [w for w in load_banned(config) if w.lower() not in already]
        terms = list(expand_replacements({t: t for t in terms}))
        dictionary_pattern = build_word_pattern(terms)
        if dictionary_pattern:
            seen = set()
            for match in dictionary_pattern.finditer(prose):
                found = " ".join(match.group(0).split())
                if found.lower() in seen:
                    continue
                seen.add(found.lower())
                slips.append((
                    "banned_word",
                    "Not approved: \"%s\"" % found,
                    penalties.get("banned_word", 1),
                ))

    para_limit = config.get("max_paragraph_sentences", 6)
    for block in re.split(r"\n\s*\n", prose):
        block_sentences = get_sentences(unwrap(block))
        if len(block_sentences) > para_limit:
            slips.append((
                "long_paragraph",
                "%d-sentence paragraph: \"%s\""
                % (len(block_sentences), snippet(block_sentences[0], 32)),
                penalties["long_paragraph"],
            ))

    # Total the penalties, but cap what any single rule can take off.
    by_rule = {}
    for rule, _message, penalty in slips:
        by_rule[rule] = by_rule.get(rule, 0) + penalty
    deduction = sum(min(value, cap) for value in by_rule.values())
    score = max(0, 100 - deduction)

    if score >= config.get("pass_score", 90):
        grade = "PASS"
    elif score >= config.get("weak_score", 70):
        grade = "WEAK"
    else:
        grade = "FAIL"

    # Order the slips one rule at a time, costliest rule first. The card shows
    # only the first few, so this makes it name several different problems
    # instead of the same problem several times.
    grouped = {}
    for rule, message, penalty in slips:
        grouped.setdefault(rule, []).append(message)
    order = sorted(by_rule, key=lambda rule: -by_rule[rule])
    ordered = []
    index = 0
    while len(ordered) < len(slips):
        for rule in order:
            bucket = grouped[rule]
            if index < len(bucket):
                ordered.append((rule, bucket[index]))
        index += 1

    return {
        "skipped": False,
        "score": score,
        "grade": grade,
        "words": total_words,
        "sentences": len(sentences),
        "counts": {rule: sum(1 for s in slips if s[0] == rule) for rule in by_rule},
        "slips": [message for _rule, message in ordered],
    }


# --- per-session state -----------------------------------------------------

def state_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")[:80]
    return STATE_DIR / ("%s.json" % safe)


def read_state(session_id):
    return _read_json(state_path(session_id), {})


def write_state(session_id, state, retention_days=7):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = state_path(session_id)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)
    prune_state(retention_days)


def prune_state(retention_days=7):
    """Every rule that creates a file needs a rule that removes it."""
    try:
        cutoff = time.time() - retention_days * 86400
        for old in STATE_DIR.glob("*.json"):
            if old.stat().st_mtime < cutoff:
                old.unlink()
        for stale in STATE_DIR.glob("*.tmp"):
            if stale.stat().st_mtime < cutoff:
                stale.unlink()
    except Exception:
        pass
