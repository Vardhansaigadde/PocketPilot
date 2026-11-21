# v5 test checklist: Telugu voice and Telugu replies

Start with `python run.py` and wait about a minute. On the phone, tap **EN** next to the
command box so it shows **తె** (it is remembered). The first Telugu command downloads the
Telugu speech model once (about 250 MB) and loads it (10-20 s); after that each command takes
a few seconds. Replies show and are spoken in Telugu (Settings → "Speak replies out loud").

If the phone speaks Telugu with an English accent or not at all: Android Settings → Text-to-speech
→ Google → install the Telugu voice.

## Pure Telugu

| # | Say | Expected | ✓ |
|---|-----|----------|:-:|
| 1 | నోట్‌ప్యాడ్ ఓపెన్ చెయ్యి | Notepad opens; "Notepad తెరుస్తున్నాను." | ☐ |
| 2 | వాల్యూమ్ పెంచు | Volume up; "సౌండ్ పెంచాను." | ☐ |
| 3 | సౌండ్ తగ్గించు | Volume down | ☐ |
| 4 | కిందకి స్క్రోల్ చెయ్యి | Scrolls down | ☐ |
| 5 | పైకి స్క్రోల్ చెయ్యి | Scrolls up | ☐ |
| 6 | హైదరాబాద్‌లో వాతావరణం ఎలా ఉంది | Hyderabad weather, in Telugu | ☐ |
| 7 | యూట్యూబ్‌లో తెలుగు పాటలు పెట్టు | YouTube search for తెలుగు పాటలు | ☐ |
| 8 | అమ్మకి కాల్ చెయ్యి | Approve card "Amma…కి వాట్సాప్ కాల్ చేయాలా?"; **Cancel** = no call | ☐ |
| 9 | అక్కకి హాయ్ అని మెసేజ్ పంపు | "Which Akka?" in Telugu if there are several; Approve card shows "హాయ్" | ☐ |
| 10 | (after 9) రెండు | Picks the second Akka | ☐ |
| 11 | గ్రిడ్ చూపించు | Grid appears | ☐ |
| 12 | ఆపు | Everything stops; "ఆపేశాను." | ☐ |
| 13 | వార్తలు | Headlines (key in `.env`) | ☐ |
| 14 | ల్యాప్‌టాప్ ఓపెన్ చెయ్యి | Screen turns on | ☐ |

## Telugu mixed with English

| # | Say | Expected | ✓ |
|---|-----|----------|:-:|
| 15 | స్క్రోల్ డౌన్ | Scrolls down | ☐ |
| 16 | క్లోజ్ విండో | Approve card "విండో మూసేయాలా?" | ☐ |
| 17 | నెక్స్ట్ ట్యాబ్ | Next browser tab | ☐ |
| 18 | (typed) notepad open cheyyi | Notepad opens; reply in Telugu | ☐ |
| 19 | (typed) ammaki call cheyyi | Approve card for Amma | ☐ |
| 20 | (typed) hyderabad lo weather ela undi | Hyderabad weather | ☐ |

## Switch back

| # | Do | Expected | ✓ |
|---|----|----------|:-:|
| 21 | Tap **తె** → **EN**, say "scroll down" | English speech model, English reply | ☐ |
| 22 | Say "hey jarvis" to the laptop with **తె** on | The laptop mic listens in Telugu too | ☐ |

Measured on this laptop (CPU, int8): pure Telugu clips 2–10 % character errors, 3–5 s for
6–10 s of speech. English words said inside Telugu come out in Telugu script (స్క్రోల్ డౌన్);
the common ones are mapped back to English, others go to the AI.
