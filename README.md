# Live Meeting Copilot MVP

Small Python spike for a meeting copilot that classifies utterances and answers three core questions:

1. What was the last relevant question?
2. What was the last task directed at me?
3. What should happen when a hotkey is pressed?

## Phase 1

`live_copilot.py` validates the post-transcript decision layer.

It classifies each utterance into one of:

- `question`
- `task`
- `context`
- `irrelevant`

It also tracks:

- last open question
- last task directed at the user
- whether the user's name was mentioned
- confidence scores

## Phase 2

`phase2_live_copilot.py` adds the live pipeline pieces around that logic:

- microphone input via `sounddevice`
- local speech-to-text via `faster-whisper`
- rolling in-memory transcript state
- hotkey support via `pynput` when a desktop session exists
- stdin fallback commands in headless/terminal-only environments
- WAV file mode for testing and replay

## Phase 3

`phase3_dashboard.py` adds a local web dashboard / overlay layer:

- FastAPI server with single-page dashboard UI
- shows latest question and latest task for me
- recent transcript/event list with classification badges
- manual text inject for testing
- custom search prompt against recent context
- WAV upload endpoint that transcribes and ingests audio

## Heuristics

### Question

Marked as a question when one of these is true:

- sentence ends with `?`
- starts with a question word like `wer`, `wie`, `was`, `wann`, `wo`, `warum`, `could`, `can`, `what`, `how`
- contains a clear request-for-information pattern such as `weißt du`, `kannst du sagen`, `can you tell`

### Task

Marked as a task when:

- user's name appears and an imperative/request pattern appears
- or there is a strong action phrase like `bitte`, `kannst du`, `schick`, `prüf`, `mach`, `kümmere dich`

### Context vs irrelevant

- `context` means statement that may matter later but is not actionable right now
- `irrelevant` means filler / short backchannel / weak fragment

## Run

### Phase 1

```bash
python3 /root/spikes/live-meeting-copilot-mvp/live_copilot.py
```

### Phase 2: live microphone mode

```bash
python3 /root/spikes/live-meeting-copilot-mvp/phase2_live_copilot.py --model small
```

Fallback stdin commands while live mode runs:

- `/answer`
- `/task`
- `/ask <prompt>`
- `/inject <text>`
- `/quit`

Global hotkeys work only when a desktop input session exists:

- `Cmd+Shift+A` → print last question
- `Cmd+Shift+T` → print last task

### Phase 2: file replay mode

```bash
python3 /root/spikes/live-meeting-copilot-mvp/phase2_live_copilot.py \
  --model small \
  --wav file1.wav file2.wav
```

### Phase 3: dashboard

```bash
python3 /root/spikes/live-meeting-copilot-mvp/phase3_dashboard.py --port 8877
```

Open:

```text
http://127.0.0.1:8877/
```

## Verified results in this environment

The host is headless and has **no default microphone device**, so full live capture could not be exercised here.

What was verified:

1. the Phase 2 app starts and degrades gracefully when no microphone exists
2. local Whisper models load successfully
3. WAV replay mode works end to end
4. task/question state updates work on real transcribed audio
5. the Phase 3 dashboard serves successfully and its API/UI update correctly
6. manual inject and WAV upload work through the dashboard/API

Verified examples:

- `Nico, kannst du das morgen an den Kunden schicken?` → `task`
- `Was meintest du mit dem Angebot?` → `question`
- `Das ist ein Problem mit der Champions League.` → `context`

Verified Phase 3 interactions:

- browser UI loaded with heading `Live Meeting Copilot`
- manual inject stored a `task`
- API `/api/answer` returned `LAST_QUESTION: Was meintest du mit dem Angebot?`
- API `/api/task` returned `LAST_TASK_FOR_ME: Nico, kannst du das morgen an den Kunden schicken?`
- WAV upload ingested `Was meinest du mit dem Handboot?` as a `question`

Note: for German TTS-generated samples, `small` was much more reliable than `tiny` or `base`.

## Verdict

### PARTIAL

The dashboard and replay path are built and verified. The remaining unverified part is live microphone capture plus real global hotkeys on a machine that actually exposes an input device and desktop session.

### Constraints

- real meetings need speaker diarization or at least speaker tags
- STT mistakes will reduce confidence
- headless servers may not expose a microphone or global hotkey session
- task extraction should later move from heuristics to an LLM-assisted pass when hotkey is pressed

### Recommendation for the real build

Use this heuristic layer as a fast local first pass, then escalate to Hermes/LLM only when:

- hotkey is pressed
- confidence is low
- answer/search synthesis is needed
- company/web/notes lookup is required
