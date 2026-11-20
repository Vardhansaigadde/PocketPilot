# v2 test checklist: 25 spoken commands

**Result: all passed on the phone (Spotify search was added after the first run).**

v2 is **done** when every command below works by voice from the **phone mic** and the **laptop mic** ("Hey Jarvis, …").
Tick each box after it works. Note anything that went wrong in the last column.

Start with `python run.py`, open PocketPilot on the phone, and have Notepad or a long web page open for the scrolling tests.

| # | Say | Expected | Phone | Laptop | Notes |
|---|-----|----------|:-----:|:------:|-------|
| 1 | scroll down | Page scrolls down | ☐ | ☐ | |
| 2 | scroll up a lot | Page scrolls up further | ☐ | ☐ | |
| 3 | click | Left click at the cursor | ☐ | ☐ | |
| 4 | right click | Context menu opens | ☐ | ☐ | |
| 5 | type hello from PocketPilot | Text typed in Notepad | ☐ | ☐ | |
| 6 | press enter | New line | ☐ | ☐ | |
| 7 | select all | Everything selected | ☐ | ☐ | |
| 8 | copy | Copied (paste somewhere to check) | ☐ | ☐ | |
| 9 | volume up | Volume goes up | ☐ | ☐ | |
| 10 | mute | Sound mutes / unmutes | ☐ | ☐ | |
| 11 | pause | Music/video pauses | ☐ | ☐ | |
| 12 | next song | Next track | ☐ | ☐ | |
| 13 | open notepad | Notepad opens | ☐ | ☐ | |
| 14 | open calculator | Calculator opens | ☐ | ☐ | |
| 15 | open chrome | Chrome opens | ☐ | ☐ | |
| 16 | switch app | Alt+Tab to the previous app | ☐ | ☐ | |
| 17 | show desktop | All windows minimise | ☐ | ☐ | |
| 18 | close the window | Approve card on phone; Approve closes it, Cancel doesn't | ☐ | ☐ | |
| 19 | show grid | Numbered grid appears | ☐ | ☐ | |
| 20 | click 14 | Grid hides, clicks box 14 | ☐ | ☐ | |
| 21 | weather in Hyderabad | Spoken temperature, rain chance, sunset | ☐ | ☐ | |
| 22 | air quality in Delhi | AQI and advice | ☐ | ☐ | |
| 23 | who is APJ Abdul Kalam | Short Wikipedia summary | ☐ | ☐ | needs POCKETPILOT_CONTACT |
| 24 | search YouTube for lofi music | Edge opens YouTube results | ☐ | ☐ | |
| 25 | I want to do some maths | AI (Ollama) opens Calculator | ☐ | ☐ | needs Ollama |

Bonus: websites and browser (not required for v2 to be done)

| Say | Expected | Phone | Laptop |
|-----|----------|:-----:|:------:|
| go to github | Edge opens github.com | ☐ | ☐ |
| open chatgpt | Edge opens chatgpt.com | ☐ | ☐ |
| go to github.com slash Vardhansaigadde slash PocketPilot | Your repo opens | ☐ | ☐ |
| search github for pocketpilot | GitHub search results | ☐ | ☐ |
| new tab, then go back, then refresh | Each browser key works | ☐ | ☐ |
| open notepad then type hello then press enter | Notepad opens, types, new line | ☐ | ☐ |

Also check:
- [ ] "stop" and the ■ button cancel an Approve card and hide the grid.
- [ ] The touchpad stays smooth while a voice command is being worked out.
- [ ] Fixed phrases reply in under 2 s; AI ones in under 6 s.
