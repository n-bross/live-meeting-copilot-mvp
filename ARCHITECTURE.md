# MVP architecture

## Goal

Turn a live conversation into three fast actions:

1. answer the last relevant question
2. show the last task for me
3. run a custom lookup against recent context

## Pipeline

```text
Audio input
  -> voice activity detection
  -> streaming STT
  -> rolling transcript buffer
  -> utterance classifier
  -> state store
  -> hotkey action
  -> Hermes / web / notes search
  -> answer overlay
```

## Components

### 1. Audio capture
- microphone
- optional system audio / loopback
- small chunks, e.g. 0.5 to 2 seconds

### 2. STT
- local first: faster-whisper
- cloud fallback optional
- output should be incremental segments

### 3. Rolling transcript buffer
Store the last 2 to 5 minutes:
- speaker label if available
- timestamp
- raw text
- normalized text
- classification result

### 4. Classifier
Each utterance becomes one of:
- `question`
- `task`
- `context`
- `irrelevant`

Signals:
- punctuation and question words
- imperative/task patterns
- name mention
- second-person phrasing
- short backchannel filter

### 5. State store
Keep only the latest useful items:
- `last_open_question`
- `last_task_for_me`
- `recent_context`
- optional `last_name_mention`

### 6. Hotkeys
- `Cmd+Shift+A` -> answer last question
- `Cmd+Shift+T` -> show last task for me
- `Cmd+Shift+F` -> ask custom question on context

### 7. Escalation layer
Fast local logic should decide what to send to Hermes.

Send to Hermes only when:
- hotkey is pressed
- confidence is below threshold
- web/company knowledge lookup is needed
- you want a synthesized natural-language answer

## Decision tree

### On every utterance
1. empty / filler -> `irrelevant`
2. obvious question -> `question`
3. name mention + action phrase -> `task`
4. longer statement -> `context`
5. otherwise -> `irrelevant`

### On hotkey: answer last question
1. fetch `last_open_question`
2. attach last 5 utterances as context
3. ask Hermes/search layer for short answer
4. display in overlay

### On hotkey: what do I need to do?
1. fetch `last_task_for_me`
2. summarize as one action sentence
3. display in overlay

## Real-build next step

Build a second spike that adds:
- microphone capture
- incremental STT
- simple terminal or browser overlay
- one real hotkey
