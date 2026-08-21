from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

PHASE2_PATH = Path(__file__).with_name("phase2_live_copilot.py")
spec = importlib.util.spec_from_file_location("phase2_live_copilot", PHASE2_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)

LiveMeetingCopilot = module.LiveMeetingCopilot

app = FastAPI(title="Live Meeting Copilot Dashboard")
copilot = LiveMeetingCopilot(my_names=["alex", "team"], model_name="small", language="de")


def state_payload() -> Dict[str, Any]:
    last_question = copilot.state.answer_last_question()
    last_task = copilot.state.show_last_task_for_me()
    recent = copilot.log[-12:]
    return {
        "last_question": last_question,
        "last_task": last_task,
        "recent": recent,
        "count": len(copilot.log),
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!doctype html>
<html lang='de'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Live Meeting Copilot</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b1020;
      --panel: #131a2d;
      --panel-2: #1a2340;
      --text: #e8eefc;
      --muted: #97a7d1;
      --accent: #7aa2ff;
      --ok: #7fe29b;
      --warn: #ffd166;
      --danger: #ff7b7b;
      --border: #2d3b65;
    }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      background: linear-gradient(180deg, #09101d 0%, #0f1830 100%);
      color: var(--text);
    }
    .wrap {
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px;
    }
    h1 { margin: 0 0 8px; font-size: 28px; }
    .sub { color: var(--muted); margin-bottom: 18px; }
    .grid {
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 16px;
    }
    .panel {
      background: rgba(19, 26, 45, 0.95);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.25);
    }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }
    .big { font-size: 20px; line-height: 1.4; min-height: 56px; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
    button {
      background: var(--accent);
      color: #08101f;
      border: none;
      border-radius: 12px;
      padding: 10px 14px;
      font-weight: 700;
      cursor: pointer;
    }
    button.secondary { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); }
    button.warn { background: var(--warn); }
    input, textarea {
      width: 100%; box-sizing: border-box; background: #0e1528; color: var(--text);
      border: 1px solid var(--border); border-radius: 12px; padding: 12px; font: inherit;
    }
    textarea { min-height: 120px; resize: vertical; }
    .row { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: end; }
    .recent { display: flex; flex-direction: column; gap: 10px; max-height: 520px; overflow: auto; }
    .item { background: #0d1528; border: 1px solid #243150; border-radius: 12px; padding: 12px; }
    .meta { color: var(--muted); font-size: 12px; margin-bottom: 6px; display:flex; justify-content:space-between; gap:8px; }
    .badge { border-radius: 999px; padding: 2px 8px; font-size: 11px; font-weight: 700; }
    .question { background: rgba(122,162,255,.18); color: #abc3ff; }
    .task { background: rgba(127,226,155,.16); color: var(--ok); }
    .context { background: rgba(255,209,102,.12); color: var(--warn); }
    .irrelevant { background: rgba(255,123,123,.12); color: var(--danger); }
    .status { color: var(--muted); font-size: 13px; margin-top: 10px; min-height: 18px; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class='wrap'>
    <h1>Live Meeting Copilot</h1>
    <div class='sub'>Phase 3 dashboard: transcript state, quick actions, manual inject, and WAV upload.</div>

    <div class='grid'>
      <div style='display:flex; flex-direction:column; gap:16px;'>
        <div class='panel'>
          <div class='label'>Letzte Frage</div>
          <div class='big' id='last-question'>—</div>
          <div class='actions'>
            <button onclick='refreshAnswer()'>Antwort holen</button>
            <button class='secondary' onclick='refreshState()'>Aktualisieren</button>
          </div>
        </div>

        <div class='panel'>
          <div class='label'>Letzte Aufgabe für mich</div>
          <div class='big' id='last-task'>—</div>
          <div class='actions'>
            <button class='warn' onclick='refreshTask()'>Aufgabe zeigen</button>
          </div>
        </div>

        <div class='panel'>
          <div class='label'>Manuell Text injizieren</div>
          <textarea id='inject-text' placeholder='z. B. Nico, kannst du das morgen an den Kunden schicken?'></textarea>
          <div class='row'>
            <input id='speaker' value='manual' placeholder='Sprecher'>
            <button onclick='injectText()'>Hinzufügen</button>
          </div>
        </div>

        <div class='panel'>
          <div class='label'>Custom Search / Nachfrage</div>
          <div class='row'>
            <input id='ask-text' placeholder='Was muss ich als Nächstes beantworten?'>
            <button class='secondary' onclick='askCustom()'>Suchen</button>
          </div>
          <div class='big' id='ask-result' style='font-size:16px; margin-top:12px;'>—</div>
        </div>

        <div class='panel'>
          <div class='label'>WAV hochladen und transkribieren</div>
          <div class='row'>
            <input id='wav-file' type='file' accept='.wav,audio/wav'>
            <button class='secondary' onclick='uploadWav()'>Upload</button>
          </div>
          <div class='status' id='status'>Bereit.</div>
        </div>
      </div>

      <div class='panel'>
        <div class='label'>Letzte Einträge</div>
        <div id='count' class='sub' style='margin:0 0 10px;'>0 Einträge</div>
        <div class='recent' id='recent'></div>
      </div>
    </div>
  </div>

<script>
async function api(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

function renderItem(item) {
  const kind = item.classification.kind;
  return `
    <div class="item">
      <div class="meta">
        <span>${item.timestamp} · ${item.speaker}</span>
        <span class="badge ${kind}">${kind}</span>
      </div>
      <div>${item.text}</div>
      <div class="meta" style="margin-top:8px; display:block;">${item.classification.reason} · confidence ${item.classification.confidence.toFixed(2)}</div>
    </div>`;
}

async function refreshState() {
  const data = await api('/api/state');
  document.getElementById('last-question').textContent = data.last_question || '—';
  document.getElementById('last-task').textContent = data.last_task || '—';
  document.getElementById('count').textContent = `${data.count} Einträge`;
  document.getElementById('recent').innerHTML = data.recent.slice().reverse().map(renderItem).join('');
}

async function refreshAnswer() {
  const data = await api('/api/answer');
  document.getElementById('last-question').textContent = data.result || '—';
}

async function refreshTask() {
  const data = await api('/api/task');
  document.getElementById('last-task').textContent = data.result || '—';
}

async function injectText() {
  const text = document.getElementById('inject-text').value.trim();
  const speaker = document.getElementById('speaker').value.trim() || 'manual';
  if (!text) return;
  await api('/api/inject', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text, speaker})
  });
  document.getElementById('inject-text').value = '';
  document.getElementById('status').textContent = 'Text übernommen.';
  await refreshState();
}

async function askCustom() {
  const prompt = document.getElementById('ask-text').value.trim();
  if (!prompt) return;
  const data = await api('/api/ask', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({prompt})
  });
  document.getElementById('ask-result').textContent = data.result || '—';
}

async function uploadWav() {
  const input = document.getElementById('wav-file');
  if (!input.files.length) return;
  const formData = new FormData();
  formData.append('file', input.files[0]);
  formData.append('speaker', 'upload');
  document.getElementById('status').textContent = 'Transkribiere...';
  const res = await fetch('/api/upload-wav', { method: 'POST', body: formData });
  const data = await res.json();
  document.getElementById('status').textContent = data.message || 'Fertig.';
  await refreshState();
}

refreshState();
setInterval(refreshState, 3000);
</script>
</body>
</html>"""


@app.get("/api/state")
def api_state() -> Dict[str, Any]:
    return state_payload()


@app.get("/api/answer")
def api_answer() -> Dict[str, Any]:
    return {"result": copilot.state.answer_last_question()}


@app.get("/api/task")
def api_task() -> Dict[str, Any]:
    return {"result": copilot.state.show_last_task_for_me()}


@app.post("/api/inject")
def api_inject(payload: Dict[str, str]) -> Dict[str, Any]:
    text = (payload.get("text") or "").strip()
    speaker = (payload.get("speaker") or "manual").strip() or "manual"
    if not text:
        return JSONResponse(status_code=400, content={"error": "text required"})
    classification = copilot.process_text(text, speaker=speaker)
    return {"ok": True, "classification": classification.__dict__}


@app.post("/api/ask")
def api_ask(payload: Dict[str, str]) -> Dict[str, Any]:
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "prompt required"})
    return {"result": copilot.state.search_custom(prompt)}


@app.post("/api/upload-wav")
async def api_upload_wav(file: UploadFile = File(...), speaker: str = Form("upload")) -> Dict[str, Any]:
    suffix = Path(file.filename or "upload.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        temp_path = Path(tmp.name)
    try:
        texts: List[str] = copilot.process_wav_file(str(temp_path), speaker=speaker)
    finally:
        temp_path.unlink(missing_ok=True)
    return {"ok": True, "segments": texts, "message": f"{len(texts)} Segment(e) verarbeitet."}


@app.get("/api/export-log")
def api_export_log() -> Dict[str, Any]:
    return {"entries": copilot.log}


def build_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="Phase 3 dashboard for the live meeting copilot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    return parser


if __name__ == "__main__":
    import uvicorn

    args = build_parser().parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
