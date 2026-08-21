# MacBook Test Plan for Today's Termin

## Goal

Get to a **yes/no** answer fast:

1. does local STT run on the MacBook?
2. does the microphone get picked up?
3. does the dashboard update live?
4. do the last-question / last-task actions work during a real conversation?

---

## 0. Copy the project to the MacBook

Put this folder on the MacBook:

```text
/root/spikes/live-meeting-copilot-mvp
```

If you move it somewhere else, replace the path in the commands below.

---

## 1. Install system dependencies

### If Homebrew is not installed

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Install runtime dependencies

```bash
brew install python portaudio ffmpeg
```

Why:
- `portaudio` -> microphone input for `sounddevice`
- `ffmpeg` -> useful for replay/testing audio conversion
- `python` -> isolated venv for today's test

---

## 2. Create a fresh venv

```bash
cd ~/live-meeting-copilot-mvp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-mac.txt
```

---

## 3. Fast smoke test: imports only

```bash
python smoke_test.py
```

Expected:
- all dependency checks say `OK`
- microphone devices list appears

If microphone list is empty, the app will not work live yet.

---

## 4. Dashboard test first

Start the dashboard:

```bash
python phase3_dashboard.py --port 8877
```

Open in browser:

```text
http://127.0.0.1:8877/
```

### Success condition
- page loads
- you can inject text manually
- the right panel shows entries
- latest task / latest question update

### Manual inject test cases

Paste these one by one into the dashboard:

#### Task test
```text
Nico, kannst du das morgen an den Kunden schicken?
```
Expected:
- classified as `task`
- `LAST_TASK_FOR_ME` updates

#### Question test
```text
Was meintest du mit dem Angebot?
```
Expected:
- classified as `question`
- `LAST_QUESTION` updates

#### Context test
```text
Das ist ein Problem mit der Champions League.
```
Expected:
- classified as `context`
- should **not** replace the last question/task

If this part works, the UI and state logic are fine.

---

## 5. Replay audio test before live mic

If you have a WAV sample on the MacBook, run:

```bash
python phase2_live_copilot.py --model small --wav your_sample.wav
```

Or use the dashboard WAV upload.

### Success condition
- transcript appears
- it is classified sensibly

This is your low-risk pre-meeting fallback if live microphone acts up.

---

## 6. Live microphone test

Run:

```bash
python phase2_live_copilot.py --model small
```

Then say out loud test sentences.

### Say these exact phrases

1. Task:
```text
Nico, kannst du das morgen an den Kunden schicken?
```

2. Question:
```text
Was meintest du mit dem Angebot?
```

3. Context:
```text
Das ist ein Problem mit der Champions League.
```

### Success condition
- terminal prints transcript chunks
- task phrase updates last task
- question phrase updates last question
- context phrase stays context

---

## 7. Real-world meeting test for today

Use this exact test sequence before the appointment:

### Option A — safest
1. Start `phase3_dashboard.py`
2. Keep browser open on the dashboard
3. Start `phase2_live_copilot.py --model small` in a second terminal
4. During a mock conversation, speak 3-5 short sentences
5. Check whether the dashboard state matches what was said

### Option B — if hotkeys matter
After live mic works, test hotkeys:
- `Cmd+Shift+A` -> last question
- `Cmd+Shift+T` -> last task

If hotkeys do not fire on macOS, check:
- System Settings -> Privacy & Security
- Input Monitoring
- Accessibility
- Terminal/iTerm may need permission

---

## 8. What counts as "good enough for today's termin"

Use it in the meeting if these 4 are true:

1. dashboard opens
2. microphone transcript appears
3. one question is correctly remembered
4. one task for Nico is correctly remembered

If hotkeys fail but the dashboard works, you can still use the dashboard as the visual copilot.

---

## 9. Fast fallback if live mic fails

Still salvage the demo like this:

1. keep the dashboard open
2. use manual inject during the meeting
3. or upload short recorded WAV snippets

That still proves the core product idea:
- classify speech content
- remember last question
- remember last task
- expose it quickly in the UI

---

## 10. Best command set for today

### Terminal 1
```bash
cd ~/live-meeting-copilot-mvp
source .venv/bin/activate
python phase3_dashboard.py --port 8877
```

### Terminal 2
```bash
cd ~/live-meeting-copilot-mvp
source .venv/bin/activate
python phase2_live_copilot.py --model small
```

### Browser
```text
http://127.0.0.1:8877/
```

---

## 11. If something breaks, check these first

### `PortAudio library not found`
```bash
brew install portaudio
pip install sounddevice
```

### no mic input / no device
Check macOS microphone permission for Terminal/iTerm.

### dashboard upload fails
```bash
pip install python-multipart
```

### bad German transcription
Use:
```bash
python phase2_live_copilot.py --model small
```
not `tiny`.

---

## Recommendation

For today, test in this order:

1. `smoke_test.py`
2. dashboard manual inject
3. live microphone
4. hotkeys last

That gets you to a reliable yes/no fastest.
