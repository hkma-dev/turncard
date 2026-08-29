# turncard

**Your coding agent answers you in plain, checked English on every turn.**

## 1. The problem

Coding agents write long. They reach for the technical word when a plain one
would do. You ask a simple question and you get six paragraphs, three of them
about things you did not ask about.

If you write code, you skim past it. If you do not write code, you cannot tell
the important sentence from the filler, and you end up owning something you do
not understand.

## 2. The standard

Aerospace solved this problem forty years ago.

In the late 1970s the European airlines asked the aerospace industry why
maintenance manuals were so hard to read. Engineers around the world work on
aircraft in English, and most of them do not speak it as a first language. A
sentence they read two ways can kill people.

The industry answered with a controlled language, and published the first guide
in 1986. It became ASD-STE100 Simplified Technical English in 2005. ASD still
maintains it, and Issue 9 came out on 15 January 2025.

The standard does two things. It gives writers about 900 approved words, each
with one meaning. It adds rules for sentences: keep them short, use the active
voice, name who does the action, give one instruction at a time.

The same fix works here. An engineer reading a manual in a second language and
you reading agent output have the same need: one meaning per word, short
sentences, and a named actor for every action.

## 3. Why a skill or a CLAUDE.md rule does not hold

Other projects put the standard in a `CLAUDE.md` file or in a skill, and both
drift.

A rule in `CLAUDE.md` is text near the top of the conversation. As the
conversation grows, that text moves further away and the model follows it less.
The name for this is context rot.

A skill is worse. A skill is a file of instructions that loads only when
something calls for it, and nothing calls for it on turn forty.

Neither one reads the answer afterwards. Nothing tells you when the model
drifted, so the rule stops working and the output looks the same as it did when
the rule still held.

## 4. What turncard does

turncard checks every answer with two hooks. A hook is a small program your
agent runs by itself at a fixed point in the turn. You never call it.

```
you ──▶ [card_hook adds the rules] ──▶ model ──▶ answer ──▶ [score_hook grades it]
          ▲                                                          │
          └────────── every fault it finds goes on the next card ────┘
```

- **`card_hook.py`** runs when you press Enter. It adds the card to your prompt.
  The card is a short block of text holding your rules, plus the faults from the
  last answer.
- **`score_hook.py`** runs when the answer ends. It grades the answer and
  records every fault it finds.

turncard sends the rules again on every prompt, so they never drift away. The
scorer reads every answer, so nothing goes unchecked. The scorer is a plain
program. It makes no model call and no network call, and it runs in about 3
milliseconds.

`card_hook.py` closes the card with one instruction: "Apply this silently. Do
not narrate the card in your reply." That stops the model prefacing every answer
with "per the card". Ask about the card and the model will tell you.

**Credit.** We took the two-hook loop from an idea Kem at GlitchCatclub
published on their socials. You can find Kem on Instagram at
[@kem_glitch](https://www.instagram.com/kem_glitch/).

## 5. What it costs

turncard adds context to every prompt. That is the whole point, and you pay for
it.

The card stays in the conversation history, so the model reads it again on every
later turn. We cut the card down to keep that cheap. It is **220 tokens**.

We measured the result over 52 real sessions on a Claude Max 20x account,
roughly 3,600 prompts:

| Card size | Extra tokens |
|-----------|--------------|
| 470 tokens (our first draft) | 6.7% |
| **220 tokens (what ships)** | **3.2%** |

So turncard costs you about **3% more of your weekly limit**. The real figure is
lower. Claude Code throws away the oldest part of a long conversation to make
room, which takes old cards with it, and our number counts every card as if it
stayed.

Write your own card and keep it short, because card size sets this cost.

## 6. Install

### Claude Code

Copy this into your agent:

```
Install turncard from https://github.com/hkma-dev/turncard

1. Clone it into a folder I will keep, and tell me where you put it.
2. Read every file first. Tell me in plain words what each one does, and
   what runs on my machine.
3. Add the two hooks from adapters/claude-code/settings.json to my
   ~/.claude/settings.json.
   Keep every hook I already have. Show me the change before you write it.
4. Run tests/verify.py and show me the result.
5. Tell me how to turn it off again.
```

You need Python 3.8 or later. The change takes effect on your next prompt, and
nothing needs a restart.

To check it works, ask for an answer in heavy corporate language. `score_hook.py`
prints one line under it:

```
STE 61/100 (FAIL) - Passive: "is triggered"
```

After a clean answer it prints nothing.

### Other agents

The scorer knows nothing about Claude Code. It takes text and hands back a list
of faults. Only the two hook files speak to one agent, and they run to 75 and
115 lines. Any agent that can do these two things can run turncard:

- run a program before the model answers, and add its output to the context
- run a program afterwards, and hand it the answer text

| Agent | Adapter | State |
|-------|---------|-------|
| **Claude Code** | `adapters/claude-code/` | Tested. This is the one we run |
| **Codex CLI** | `adapters/codex/` | Written, **untested**. Its `Stop` hook carries `last_assistant_message` under that same name |
| **Gemini CLI** | `adapters/gemini/` | Written, **untested**. `BeforeAgent` adds context, `AfterAgent` hands over `prompt_response` |
| **Cursor** | none | Half possible. `afterAgentResponse` grades an answer, and no documented event adds the card to the next prompt |
| **opencode** | none | Half possible. The plugin API covers both halves, and version 2 renames it |
| **aider** | none | No hook system |
| **Your own loop** | none needed | Call `engine.build_card()` before the model and `engine.record_answer()` after |

Each adapter folder holds its own config example. We wrote the Codex and Gemini
adapters against each product's published hook schemas, and we have not run
either one. Tell us what breaks.

## 7. Screen it before you install it

These hooks read every prompt you send and every answer you get. Never install
anything with that reach, from us or from anybody, without looking at it first.

Step 2 of the install prompt makes your agent read the code and explain it. Ask
it to audit the repository as well. It costs you one turn.

`tests/verify.py` runs 19 checks. Run it after you install, and again whenever
you change a rulepack.

## 8. Feedback

Open an issue on the repository. More to come.

---

# Reference

## The rulepack

`rulepacks/ste` is the example that ships. Nothing in the engine knows about
STE, so you can write rules for anything: a house style guide, a review
checklist or a security rule set.

A rulepack is two files.

| File | What it holds |
|------|---------------|
| `<name>.md` | The rules the model reads every turn. Keep it short. |
| `<name>.lexicon.json` | `replace` maps a word to a plainer word. `avoid` lists words to delete. |

Drop yours in `rulepacks/`, then point `rulepack` in `config.json` at it.

## What the scorer checks

| Rule | What it finds | Points |
|------|---------------|--------|
| Long sentence | More than `max_sentence_words` | 3 |
| Passive voice | "is changed", "was written", "be performed" | 4 |
| Progressive tense | "is running", "are being started" | 2 |
| Word choice | A word in `replace`, and its other forms | 2 |
| Filler word | A word in `avoid` | 1 |
| Semicolon | Two sentences joined into one | 2 |
| Long paragraph | More than `max_paragraph_sentences` | 2 |

The score starts at 100. Each mistake takes points off. `max_penalty_per_rule`
caps what any one rule can remove, so the penalty for one bad habit cannot mask
the other rules.

**It ignores code.** The scorer strips fenced blocks, inline code, file paths
and links before it reads anything, so the rules apply to prose only.

**Short answers get no score.** Under `min_words_to_score` words of prose the
last score stays, so a short "Done." does not erase real feedback.

**Some rules need a reader.** One word for one meaning, noun clusters and one
instruction per sentence sit beyond a regular expression. The card carries them
and the model follows them. A score of 100 means the scorer found no fault it
can detect, not that the prose is perfect.

## Settings

Everything lives in `config.json`. Every change takes effect on the next prompt.

| Key | Default | What it does |
|-----|---------|--------------|
| `enabled` | `true` | Set to `false` to turn turncard off. |
| `rulepack` | `rulepacks/ste` | Which rules to load. |
| `mode` | `feedforward` | `strict` makes the model rewrite a failing answer in the same turn, once per turn so it cannot loop, at the cost of more tokens. |
| `show_score` | `on_slip` | `always` or `never` also work. |
| `max_slips_on_card` | `3` | How many slips the next card names. |
| `state_retention_days` | `7` | turncard deletes session files older than this. |

## Failure behaviour

Both hooks exit 0 on any error and print nothing. A broken card, a missing
rulepack or a bad `config.json` cannot break your session.

## About the ASD-STE100 dictionary

The standard names about 900 words it does not approve, each with an approved
alternative. **This repository ships none of them.** ASD gives the standard away
and forbids redistribution.

`tools/extract_ste_words.py` reads your own copy of the PDF and writes
`rulepacks/ste.banned.json` on your machine. `.gitignore` keeps that file out of
git. Set `use_banned_list` to `true` to switch it on.

It is noisy outside aerospace. The standard marks ordinary software words as not
approved: file, hook, key, state, next, build, call, case. On clean prose it
produced eight false alarms and hid the one real mistake. The hand-written
`replace` and `avoid` lists in the lexicon do the useful work.

The extractor takes the words only, never the approved alternatives. In the PDF
the word column and the alternative column drift apart where a row wraps, so
pairing them by position mismatches rows. A bad pair would teach the model the
wrong replacement.

## License

MIT. See `LICENSE`. The two hooks and the engine need nothing beyond the Python
standard library.

`tools/extract_ste_words.py` is the exception. It needs PyMuPDF, which carries
AGPL-3.0 or a paid commercial licence. The tool runs on your machine, stays out
of the hook path, and turncard never bundles it. Bundle PyMuPDF into a
redistributed artefact and you take on the AGPL terms yourself.

ASD-STE100 is a trademark of the AeroSpace and Defence Industries Association of
Europe. This project has no affiliation with ASD, and it does not redistribute
the standard.
