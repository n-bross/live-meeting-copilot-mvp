from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
from faster_whisper import WhisperModel

try:
    import sounddevice as sd
except Exception as exc:  # pragma: no cover - import fallback for degraded environments
    sd = None
    SOUNDDEVICE_IMPORT_ERROR = exc
else:
    SOUNDDEVICE_IMPORT_ERROR = None

try:
    from pynput import keyboard as pynput_keyboard
except Exception:
    pynput_keyboard = None

QUESTION_WORDS = {
    "wer", "wie", "was", "wann", "wo", "warum", "wieso", "weshalb",
    "welche", "welcher", "welches", "is", "are", "what", "why", "when",
    "where", "who", "how", "can", "could", "would", "do", "does", "did"
}

NAME_HINTS_DEFAULT = ["alex", "team"]

TASK_PATTERNS = [
    r"\bbitte\b",
    r"\bkannst du\b",
    r"\bkönntest du\b",
    r"\bcan you\b",
    r"\bcould you\b",
    r"\bschick\b",
    r"\bsende\b",
    r"\bprüf\b",
    r"\bpruef\b",
    r"\bcheck\b",
    r"\bmach\b",
    r"\bkümmere dich\b",
    r"\bkuemmere dich\b",
    r"\bfollow[- ]?up\b",
    r"\bübernimm\b",
    r"\buebernimm\b",
]

QUESTION_PATTERNS = [
    r"\bweißt du\b",
    r"\bweisst du\b",
    r"\bkannst du sagen\b",
    r"\bcan you tell\b",
    r"\bdo you know\b",
    r"\bwas meinst du\b",
]

IRRELEVANT_PATTERNS = [
    r"^hm+$",
    r"^mhm+$",
    r"^okay$",
    r"^ok$",
    r"^ja$",
    r"^yes$",
    r"^nein$",
    r"^no$",
]


@dataclass
class Utterance:
    speaker: str
    text: str
    timestamp: str = ""


@dataclass
class Classification:
    kind: str
    confidence: float
    directed_to_me: bool
    mentions_me: bool
    reason: str


@dataclass
class TrackedItem:
    utterance: Utterance
    classification: Classification


@dataclass
class LiveCopilotState:
    my_names: List[str] = field(default_factory=lambda: NAME_HINTS_DEFAULT.copy())
    history: List[TrackedItem] = field(default_factory=list)
    last_open_question: Optional[TrackedItem] = None
    last_task_for_me: Optional[TrackedItem] = None

    def ingest(self, utterance: Utterance) -> Classification:
        classification = classify_utterance(utterance.text, self.my_names)
        tracked = TrackedItem(utterance=utterance, classification=classification)
        self.history.append(tracked)

        if classification.kind == "question" and classification.confidence >= 0.6:
            self.last_open_question = tracked

        if classification.kind == "task" and classification.directed_to_me and classification.confidence >= 0.6:
            self.last_task_for_me = tracked

        return classification

    def answer_last_question(self) -> Optional[str]:
        if not self.last_open_question:
            return None
        u = self.last_open_question.utterance
        return f"LAST_QUESTION: {u.text}"

    def show_last_task_for_me(self) -> Optional[str]:
        if not self.last_task_for_me:
            return None
        u = self.last_task_for_me.utterance
        return f"LAST_TASK_FOR_ME: {u.text}"

    def search_custom(self, prompt: str) -> str:
        context = self.history[-5:]
        joined = " | ".join(f"{item.utterance.speaker}: {item.utterance.text}" for item in context)
        return f"CUSTOM_SEARCH_PROMPT: {prompt}\nRECENT_CONTEXT: {joined}"


class WhisperTranscriber:
    def __init__(self, model_name: str = "tiny", language: str = "de") -> None:
        self.model_name = model_name
        self.language = language
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe_segments(self, wav_path: str) -> List[str]:
        segments, _ = self.model.transcribe(
            wav_path,
            language=self.language,
            vad_filter=True,
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
        )
        return [normalize_spacing(segment.text) for segment in segments if segment.text and segment.text.strip()]

    def transcribe_wav(self, wav_path: str) -> str:
        return normalize_spacing(" ".join(self.transcribe_segments(wav_path)))


class AudioRecorder:
    def __init__(self, samplerate: int = 16000, channels: int = 1, chunk_seconds: float = 4.0) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.chunk_seconds = chunk_seconds
        self.audio_queue: "queue.Queue[np.ndarray]" = queue.Queue()
        self.stream = None

    def available(self) -> Tuple[bool, str]:
        if sd is None:
            return False, f"sounddevice unavailable: {SOUNDDEVICE_IMPORT_ERROR}"
        try:
            devices = sd.query_devices()
            default_in, _ = sd.default.device
            if default_in is None or int(default_in) < 0:
                return False, "no default input device"
            if len(devices) == 0:
                return False, "no audio devices found"
            return True, "ok"
        except Exception as exc:
            return False, str(exc)

    def start(self) -> None:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(f"Audio unavailable: {reason}")

        blocksize = int(self.samplerate * self.chunk_seconds)

        def callback(indata, frames, time_info, status):
            if status:
                print(f"[audio-status] {status}", file=sys.stderr)
            self.audio_queue.put(indata.copy())

        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            blocksize=blocksize,
            callback=callback,
        )
        self.stream.start()

    def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def normalize_spacing(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def classify_utterance(text: str, my_names: List[str]) -> Classification:
    norm = normalize(text)
    mentions_me = any(name in norm for name in my_names)
    directed_to_me = mentions_me

    if not norm:
        return Classification("irrelevant", 0.0, False, False, "empty")

    if any(re.match(pattern, norm) for pattern in IRRELEVANT_PATTERNS):
        return Classification("irrelevant", 0.95, False, mentions_me, "short backchannel")

    question_score, question_reason = detect_question(norm)
    task_score, task_reason, directed_to_me = detect_task(norm, mentions_me)

    if task_score >= 0.75 and mentions_me:
        return Classification("task", task_score, directed_to_me, mentions_me, task_reason)

    if question_score >= 0.75 and question_score >= task_score:
        return Classification("question", question_score, directed_to_me, mentions_me, question_reason)

    if task_score >= 0.75:
        return Classification("task", task_score, directed_to_me, mentions_me, task_reason)

    if len(norm.split()) <= 3:
        return Classification("irrelevant", 0.6, directed_to_me, mentions_me, "too short and non-actionable")

    return Classification("context", 0.65, directed_to_me, mentions_me, "stored as conversational context")


def detect_question(norm: str) -> Tuple[float, str]:
    if norm.endswith("?"):
        return 0.95, "question mark"

    first = norm.split()[0]
    if first in QUESTION_WORDS:
        return 0.82, f"starts with question word '{first}'"

    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, norm):
            return 0.8, f"matched question pattern '{pattern}'"

    return 0.0, "no question signal"


def detect_task(norm: str, mentions_me: bool) -> Tuple[float, str, bool]:
    score = 0.0
    reasons = []
    directed_to_me = mentions_me

    if mentions_me:
        score += 0.35
        reasons.append("mentions my name")

    matched_patterns = 0
    for pattern in TASK_PATTERNS:
        if re.search(pattern, norm):
            score += 0.25 if matched_patterns == 0 else 0.15
            matched_patterns += 1
            reasons.append(f"matched task pattern '{pattern}'")
            if matched_patterns >= 2:
                break

    if norm.endswith("!"):
        score += 0.1
        reasons.append("exclamation emphasis")

    if any(re.search(rf"\b{word}\b", norm) for word in ["du", "dir", "dein", "deine"]):
        score += 0.15
        directed_to_me = True
        reasons.append("second-person phrasing")

    if score > 0:
        return min(score, 0.95), ", ".join(reasons), directed_to_me

    return 0.0, "no task signal", directed_to_me


class LiveMeetingCopilot:
    def __init__(self, my_names: List[str], model_name: str = "tiny", language: str = "de") -> None:
        self.state = LiveCopilotState(my_names=my_names)
        self.transcriber = WhisperTranscriber(model_name=model_name, language=language)
        self.log: List[dict] = []
        self.running = False

    def process_text(self, text: str, speaker: str = "speaker") -> Classification:
        utterance = Utterance(speaker=speaker, text=text, timestamp=time.strftime("%H:%M:%S"))
        classification = self.state.ingest(utterance)
        entry = {
            "timestamp": utterance.timestamp,
            "speaker": speaker,
            "text": text,
            "classification": asdict(classification),
        }
        self.log.append(entry)
        print(f"[{utterance.timestamp}] [{speaker}] {text}")
        print(f"  -> kind={classification.kind} confidence={classification.confidence:.2f} mentions_me={classification.mentions_me} directed_to_me={classification.directed_to_me}")
        print(f"  -> reason={classification.reason}")
        return classification

    def process_wav_file(self, wav_path: str, speaker: str = "speaker") -> List[str]:
        texts = self.transcriber.transcribe_segments(wav_path)
        if not texts:
            print(f"[skip] no speech detected in {wav_path}")
            return []
        for text in texts:
            self.process_text(text, speaker=speaker)
        return texts

    def write_log(self, path: str) -> None:
        Path(path).write_text(json.dumps(self.log, indent=2, ensure_ascii=False))


def write_temp_wav(samples: np.ndarray, samplerate: int) -> str:
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    if pcm.ndim == 1:
        pcm = pcm[:, None]

    fd, path = tempfile.mkstemp(suffix=".wav", prefix="copilot_chunk_")
    os.close(fd)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(pcm.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(pcm.tobytes())
    return path


def start_hotkeys(copilot: LiveMeetingCopilot) -> Optional[object]:
    if pynput_keyboard is None or not os.environ.get("DISPLAY"):
        print("[hotkeys] global hotkeys unavailable; using stdin commands")
        return None

    current_keys = set()

    def on_press(key):
        current_keys.add(key)
        cmd = pynput_keyboard.Key.cmd
        shift = pynput_keyboard.Key.shift
        if cmd in current_keys and shift in current_keys:
            if hasattr(key, "char") and key.char:
                if key.char.lower() == "a":
                    print(copilot.state.answer_last_question() or "LAST_QUESTION: none")
                elif key.char.lower() == "t":
                    print(copilot.state.show_last_task_for_me() or "LAST_TASK_FOR_ME: none")

    def on_release(key):
        current_keys.discard(key)

    listener = pynput_keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    print("[hotkeys] Cmd+Shift+A => last question, Cmd+Shift+T => last task")
    return listener


def run_file_mode(args: argparse.Namespace) -> int:
    copilot = LiveMeetingCopilot(my_names=args.names, model_name=args.model, language=args.language)
    for wav_path in args.wav:
        copilot.process_wav_file(wav_path, speaker=args.speaker)
    if args.log_json:
        copilot.write_log(args.log_json)
    print(copilot.state.answer_last_question() or "LAST_QUESTION: none")
    print(copilot.state.show_last_task_for_me() or "LAST_TASK_FOR_ME: none")
    return 0


def run_live_mode(args: argparse.Namespace) -> int:
    recorder = AudioRecorder(chunk_seconds=args.chunk_seconds)
    ok, reason = recorder.available()
    if not ok:
        print(f"Microphone mode unavailable: {reason}")
        print("Use --wav file1.wav [file2.wav ...] for verification in this environment.")
        return 2

    copilot = LiveMeetingCopilot(my_names=args.names, model_name=args.model, language=args.language)
    hotkey_listener = start_hotkeys(copilot)
    recorder.start()
    print("Live mode started.")
    print("Type /answer, /task, /ask <prompt>, /quit in stdin fallback mode.")

    stop_event = threading.Event()

    def worker() -> None:
        while not stop_event.is_set():
            try:
                chunk = recorder.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            wav_path = write_temp_wav(chunk, recorder.samplerate)
            try:
                copilot.process_wav_file(wav_path)
            finally:
                Path(wav_path).unlink(missing_ok=True)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    try:
        while True:
            command = input().strip()
            if command == "/quit":
                break
            if command == "/answer":
                print(copilot.state.answer_last_question() or "LAST_QUESTION: none")
            elif command == "/task":
                print(copilot.state.show_last_task_for_me() or "LAST_TASK_FOR_ME: none")
            elif command.startswith("/ask "):
                print(copilot.state.search_custom(command[5:]))
            elif command.startswith("/inject "):
                copilot.process_text(command[8:], speaker="manual")
            elif command:
                print("Unknown command. Use /answer /task /ask <prompt> /inject <text> /quit")
    finally:
        stop_event.set()
        recorder.stop()
        if hotkey_listener is not None:
            hotkey_listener.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 2 live meeting copilot: mic + whisper + hotkey/stdin actions")
    parser.add_argument("--wav", nargs="*", default=[], help="Transcribe one or more WAV files instead of using the microphone")
    parser.add_argument("--speaker", default="speaker", help="Speaker label for file mode")
    parser.add_argument("--model", default="tiny", help="faster-whisper model name")
    parser.add_argument("--language", default="de", help="language hint for whisper")
    parser.add_argument("--chunk-seconds", type=float, default=4.0, help="microphone chunk length")
    parser.add_argument("--names", nargs="+", default=NAME_HINTS_DEFAULT.copy(), help="names that count as me")
    parser.add_argument("--log-json", default="", help="optional JSON log output path")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.wav:
        return run_file_mode(args)
    return run_live_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
