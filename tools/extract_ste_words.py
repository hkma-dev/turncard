"""Build a banned-word list from your own copy of the ASD-STE100 PDF.

    pip install pymupdf
    python tools/extract_ste_words.py path/to/ASD-STE100_ISSUE9.pdf

LICENCE NOTE
turncard is MIT, but PyMuPDF is AGPL-3.0 or commercial. This tool runs on your
machine and sits outside the hook path, so the MIT hooks stay clean. Bundle
PyMuPDF into anything you redistribute and the AGPL terms follow it.

Writes rulepacks/ste.banned.json, which .gitignore keeps out of git. Then set
"use_banned_list": true in config.json.

WHY THIS IS A SCRIPT AND NOT A DATA FILE
ASD gives the standard away and forbids redistribution, so turncard ships no
word list. You run this against the copy you obtained yourself, and the output
stays on your machine.

WHAT IT EXTRACTS, AND WHAT IT SKIPS
Only column 1 of the Part 2 dictionary: the headwords. The standard states that
"a word in lowercase letters is not approved in STE", so a lowercase headword is
unambiguous on its own.

It does NOT take the approved alternatives in column 2. Rows wrap, and the two
columns drift apart vertically, so pairing them by position mismatches rows. For
example, "account for" pairs with the alternative of a different row. A bad pair
teaches the wrong replacement, so turncard tells the model only that a word is
not approved, and the model chooses the plain word itself.

BE WARNED
The list is noisy outside aerospace. It marks ordinary software words as not
approved: file, hook, key, state, next, build, call, case. Leave
"use_banned_list" off unless you write aircraft documentation.
"""

import json
import re
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:
    sys.exit("pymupdf is missing. Run: pip install pymupdf")

REPO = Path(__file__).resolve().parent.parent
COL1_MAX = 175          # column 1 sits at x=72, column 2 at x=180
BAND = 3.0              # the two columns sit ~1.5pt apart vertically
POS = r"(?:n|v|adj|adv|pre|conj|art|pn|int|num)"
HEAD = re.compile(r"^([a-z][a-z'\- ]{2,24}?)\s*\((" + POS + r")\)$")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__.strip().splitlines()[0] + "\n\n"
                 "Usage: python tools/extract_ste_words.py <ASD-STE100.pdf> "
                 "[output.json]")

    pdf = Path(argv[1]).expanduser()
    if not pdf.is_file():
        sys.exit("No such file: %s" % pdf)
    out = Path(argv[2]).expanduser() if len(argv) > 2 else REPO / "rulepacks" / "ste.banned.json"

    doc = pymupdf.open(pdf)
    words = set()
    pages = 0

    for page in doc:
        text = page.get_text("text")
        if "Part 2" not in text or "Dictionary" not in text:
            continue
        pages += 1
        rows = {}
        for x0, y0, _x1, _y1, token, *_ in page.get_text("words"):
            if x0 < COL1_MAX:
                rows.setdefault(round(y0 / BAND), []).append((x0, token))
        for items in rows.values():
            line = " ".join(t for _x, t in sorted(items)).strip()
            match = HEAD.match(line)
            if match:
                word = " ".join(match.group(1).split()).lower()
                if len(word) >= 3:
                    words.add(word)

    if not pages:
        sys.exit("Found no Part 2 dictionary pages. Is this ASD-STE100 Issue 9?")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "_source": "ASD-STE100 Part 2 Dictionary, lowercase column-1 headwords, "
                   "which the standard defines as not approved.",
        "_note": "Approved alternatives are deliberately absent. Do not "
                 "redistribute this file.",
        "banned": sorted(words),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print("pages scanned: %d" % pages)
    print("words written: %d" % len(words))
    print("output:        %s" % out)
    print('\nNow set "use_banned_list": true in config.json.')


if __name__ == "__main__":
    main(sys.argv)
