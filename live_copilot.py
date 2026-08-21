from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import re

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
    r"\bcheck\b",
    r"\bmach\b",
    r"\bkümmere dich\b",
    r"\bfollow[- ]?up\b",
    r"\bübernimm\b",
]

QUESTION_PATTERNS = [
    r"\bweißt du\b",
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


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


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


def classify_utterance(text: str, my_names: List[str]) -> Classification:
    raw = text.strip()
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


def demo() -> None:
    state = LiveCopilotState()
    samples = [
        Utterance("Alex", "Das ist ein Problem mit der Champions League."),
        Utterance("Sarah", "Nico, kannst du das morgen an den Kunden schicken?"),
        Utterance("Tom", "Wie hoch war der Umsatz letztes Jahr?"),
        Utterance("Mila", "hm"),
        Utterance("Sarah", "Leon, prüf bitte noch den Vertrag und mach ein Follow-up."),
        Utterance("Tom", "Was meintest du mit dem Angebot?"),
    ]

    for item in samples:
        c = state.ingest(item)
        print(f"[{item.speaker}] {item.text}")
        print(f"  -> kind={c.kind} confidence={c.confidence:.2f} mentions_me={c.mentions_me} directed_to_me={c.directed_to_me}")
        print(f"  -> reason={c.reason}")

    print()
    print(state.answer_last_question() or "LAST_QUESTION: none")
    print(state.show_last_task_for_me() or "LAST_TASK_FOR_ME: none")
    print(state.search_custom("What do I need to answer next?"))


if __name__ == "__main__":
    demo()
