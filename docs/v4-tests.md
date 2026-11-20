# v4 test checklist: WhatsApp, tasks, memory, new skills

Start with `python run.py` and wait about a minute. Say each command with the phone mic
(or type it). Every WhatsApp send and call shows an **Approve** card first.

## WhatsApp (try with someone who expects a test message)

| # | Say | Expected | ✓ |
|---|-----|----------|:-:|
| 1 | open my chat with amma | WhatsApp opens on Amma's chat | ☐ |
| 2 | message amma that this is a PocketPilot test | Draft typed; Approve card shows the exact text; **Cancel** clears the box | ☐ |
| 3 | message amma that this is a PocketPilot test | **Approve** sends it | ☐ |
| 4 | call amma | Approve card "Voice call Amma on WhatsApp?"; **Cancel** = no call | ☐ |
| 5 | video call amma | Approve starts a video call | ☐ |
| 6 | message kidd u that hi | Finds "Kidduuu" despite the spelling | ☐ |
| 7 | message nobody that hi | "I couldn't find nobody in WhatsApp", nothing typed | ☐ |
| 8 | (draft waiting) press ■ Stop | Draft is cleared, nothing sent | ☐ |
| 9 | call amma (with "Amma ❤️" and "Amma" both saved) | Asks: say 'amma heart' or 'just amma' | ☐ |
| 10 | message amma heart that hi | Approve card shows "Amma ❤️" | ☐ |

## Multi-step tasks

| # | Say | Expected | ✓ |
|---|-----|----------|:-:|
| 1 | open notepad and write my shopping list: milk, eggs and bread | Phone shows the plan, then each step; text appears in Notepad | ☐ |
| 2 | open calculator and work out 12 plus 30 | Calculator shows 42 | ☐ |
| 3 | open my github repo vardhansaigadde/pocketpilot and show me the issues | Repo opens, Issues tab clicked | ☐ |
| 4 | (during a task) press ■ Stop | Task stops before the next step | ☐ |

## Memory

| # | Say | Expected | ✓ |
|---|-----|----------|:-:|
| 1 | what did I do today | Lists today's commands with times | ☐ |
| 2 | what was I working on yesterday | Yesterday's commands (or "nothing recorded") | ☐ |
| 3 | clear my history | Approve card; Approve deletes it | ☐ |

## New skills

| # | Say | Expected | ✓ |
|---|-----|----------|:-:|
| 1 | convert 100 dollars to rupees | Today's rate in ₹ | ☐ |
| 2 | dollar rate | $1 in ₹ | ☐ |
| 3 | define serendipity | Meaning + example | ☐ |
| 4 | news / news about ISRO | Without a key: how to get one. With `POCKETPILOT_GNEWS_KEY`: 3 headlines | ☐ |
| 5 | cricket score | Without a key: how to get one. With `POCKETPILOT_CRICKET_KEY`: live scores | ☐ |

## Laptop awake

| # | Say | Expected | ✓ |
|---|-----|----------|:-:|
| 1 | (plugged in, wait until the screen turns off) open my laptop | Screen comes back on; the phone stayed connected | ☐ |
| 2 | keep my laptop awake | Stays awake on battery too while PocketPilot runs | ☐ |
| 3 | let my laptop sleep | Normal sleep again | ☐ |

## Safety checks
- [ ] Smart click on a "Close", "Exit", "Leave" or "End call" button asks Approve.
- [ ] Nothing is ever sent or dialled without Approve.

## Eval table (when the laptop is free, ~10 minutes)
`python scripts/eval_agent.py` → writes `docs/eval.md` for the README.
