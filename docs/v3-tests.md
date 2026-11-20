# v3 test checklist: smart click + screen explainer

v3 is **done** when smart click hits the right target on the 10 screens below, and summaries are
correct on the 5 pages. Say each command with the phone mic (or "Hey Jarvis, ...").
Start with `python run.py` and wait about a minute for the AI model to load.

## Smart click (10 screens)

| # | Open this first | Say | Expected | ✓ |
|---|-----------------|-----|----------|:-:|
| 1 | Calculator | click seven, then click plus, click two, click equals | Shows 9 | ☐ |
| 2 | Edge on github.com (signed out) | click sign in | **Approve card** on the phone; Approve opens the sign-in page | ☐ |
| 3 | Edge, any page | click the address bar *(or "address bar")* | Cursor in the address bar | ☐ |
| 4 | File Explorer | click Downloads | Downloads folder opens | ☐ |
| 5 | File Explorer | right click on Documents | Right-click menu on Documents | ☐ |
| 6 | Settings | click Bluetooth | Bluetooth page opens | ☐ |
| 7 | Notepad | click File | File menu opens | ☐ |
| 8 | YouTube in Edge | click the search button | Search box / results | ☐ |
| 9 | A web page with a cookie banner | click accept | Banner closes | ☐ |
| 10 | Any app | click unicorn | "I couldn't find unicorn… say show grid" (nothing clicked) | ☐ |

## Screen explainer (5 pages + extras)

| # | Open this first | Say | Expected | ✓ |
|---|-----------------|-----|----------|:-:|
| 1 | A Wikipedia article | summarize this page | Correct 2-3 sentence summary (about 30-40 s) | ☐ |
| 2 | A news article | summarize this page | Correct summary | ☐ |
| 3 | A GitHub README (e.g. your PocketPilot repo) | what is this page about | Correct summary | ☐ |
| 4 | A Python error in a terminal or Notepad | explain this error | Says what it means + a fix (a few seconds) | ☐ |
| 5 | A long email or document | summarize this page | Correct summary | ☐ |
| 6 | Any window | read the screen | Reads the visible text (instant) | ☐ |
| 7 | A photo or a game | what's on my screen | Describes it (about 40 s) | ☐ |

Also check:
- [ ] The phone shows "Looking at your screen…" straight away for summarize / explain / describe.
- [ ] Right after a summary, a normal voice command ("volume up") still works quickly.
- [ ] "open the command prompt" is always refused.
- [ ] Risky buttons (send, delete, pay, sign in) always ask Approve first; Cancel does nothing.
