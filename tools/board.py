#!/usr/bin/env python3
"""Team ticket board: one JSON file + a static HTML render. No server, no deps.

The board lives in the MAIN checkout (shared by every git worktree):
    <main checkout>/board/tickets.json   data (gitignored)
    <main checkout>/board/index.html     rendered on every change; open it in a browser

Usage (from any worktree):
    python3 tools/board.py list [--status doing]
    python3 tools/board.py add "Title" [--status todo] [--who backend] [--branch b] [--note "…"]
    python3 tools/board.py move T-7 doing|review|owner|done|todo [--note "…"]
    python3 tools/board.py note T-7 "short progress note"
    python3 tools/board.py set T-7 --who qa --branch claude/x --title "…" \
        --goal "why" --context "background" --ac "criterion 1; criterion 2"
    python3 tools/board.py render

Columns: todo → doing → review (ready to merge / in QA) → done; "owner" = waiting
on a decision or action by the owner. Keep titles short and notes to one line.
"""
from __future__ import annotations

import argparse
import fcntl
import html
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

COLUMNS = [
    ("todo", "To do", "Teendő"),
    ("doing", "Doing", "Folyamatban"),
    ("review", "Review / merge", "Ellenőrzés"),
    ("owner", "Waiting on owner", "Rád vár"),
    ("done", "Done", "Kész"),
]
KEYS = [c[0] for c in COLUMNS]


def board_dir() -> Path:
    env = os.environ.get("BOARD_DIR")
    if env:
        return Path(env)
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, check=True,
                                cwd=Path(__file__).resolve().parent).stdout.strip()
        return Path(common).parent / "board"
    except Exception:
        return Path(__file__).resolve().parent.parent / "board"


DIR = board_dir()
DATA = DIR / "tickets.json"
HTML_OUT = DIR / "index.html"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class Board:
    """Context manager: exclusive lock, load, (mutate), atomic save + render."""

    def __init__(self, write: bool):
        self.write = write

    def __enter__(self):
        DIR.mkdir(parents=True, exist_ok=True)
        self.lock = open(DIR / ".lock", "w")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        self.data = json.loads(DATA.read_text()) if DATA.exists() else {"next_id": 1, "tickets": []}
        return self.data

    def __exit__(self, exc_type, *_):
        try:
            if self.write and exc_type is None:
                fd, tmp = tempfile.mkstemp(dir=DIR, suffix=".json")
                with os.fdopen(fd, "w") as f:
                    json.dump(self.data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, DATA)
                render(self.data)
        finally:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock.close()


def find(data, tid: str) -> dict:
    tid = tid.upper() if tid.upper().startswith("T-") else f"T-{tid}"
    for t in data["tickets"]:
        if t["id"] == tid:
            return t
    sys.exit(f"no such ticket: {tid}")


def split_ac(ac):
    return [x.strip() for x in ac.split(";") if x.strip()] if ac else []


def render(data) -> None:
    def card(t):
        meta = " · ".join(html.escape(x) for x in (t.get("who") or "", t.get("branch") or "") if x)
        note = f'<p class="note">{html.escape(t["note"])}</p>' if t.get("note") else ""
        det = ""
        if t.get("goal") or t.get("context") or t.get("ac"):
            ac = "".join(f"<li>{html.escape(x)}</li>" for x in t.get("ac") or [])
            det = ("<details><summary>details</summary>"
                   + (f'<p><b>Goal:</b> {html.escape(t["goal"])}</p>' if t.get("goal") else "")
                   + (f'<p><b>Context:</b> {html.escape(t["context"])}</p>' if t.get("context") else "")
                   + (f"<p><b>Done when:</b></p><ul>{ac}</ul>" if ac else "") + "</details>")
        note += det
        return (f'<article class="card"><header><b>{t["id"]}</b><time>{t["updated"]}</time></header>'
                f'<h3>{html.escape(t["title"])}</h3>{note}'
                f'{f"<footer>{meta}</footer>" if meta else ""}</article>')

    cols = []
    for key, en, hu in COLUMNS:
        items = [t for t in data["tickets"] if t["status"] == key]
        items.sort(key=lambda t: t["updated"], reverse=True)
        if key == "done":
            items = items[:30]
        cols.append(f'<section class="col {key}"><h2>{en} <span>· {hu}</span><em>{len(items)}</em></h2>'
                    + "".join(card(t) for t in items) + "</section>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="30">
<title>Team board</title><style>
:root{{--bg:#f6f7f9;--fg:#1d2330;--muted:#667085;--card:#fff;--line:#e3e6ec;--todo:#94a3b8;--doing:#3b82f6;--review:#a855f7;--owner:#f59e0b;--done:#22c55e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151b;--fg:#e6e9ef;--muted:#98a2b3;--card:#1c2129;--line:#2a313c}}}}
*{{box-sizing:border-box}}body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,-apple-system,sans-serif}}
h1{{font-size:18px;margin:0 0 12px}}h1 small{{color:var(--muted);font-weight:400;font-size:13px}}
main{{display:grid;grid-template-columns:repeat(5,minmax(200px,1fr));gap:12px;align-items:start}}
@media (max-width:900px){{main{{grid-template-columns:1fr}}}}
.col{{background:transparent;border-top:4px solid var(--line);padding-top:8px}}
.col h2{{font-size:13px;text-transform:uppercase;letter-spacing:.04em;margin:0 0 8px;display:flex;gap:6px;align-items:baseline}}
.col h2 span{{color:var(--muted);text-transform:none;letter-spacing:0;font-weight:400}}.col h2 em{{margin-left:auto;font-style:normal;color:var(--muted)}}
.todo{{border-color:var(--todo)}}.doing{{border-color:var(--doing)}}.review{{border-color:var(--review)}}.owner{{border-color:var(--owner)}}.done{{border-color:var(--done)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin-bottom:8px}}
.card header{{display:flex;justify-content:space-between;color:var(--muted);font-size:12px}}
.card h3{{font-size:14px;margin:4px 0}}.note{{margin:4px 0;color:var(--muted);font-size:13px}}
details{{font-size:13px;margin:4px 0}}details summary{{cursor:pointer;color:var(--muted)}}details p,details ul{{margin:4px 0}}details ul{{padding-left:18px}}
.card footer{{font-size:12px;color:var(--muted);word-break:break-all}}.owner .card{{border-color:var(--owner)}}
</style></head><body><h1>Team board <small>updated {now()} · auto-refresh 30 s</small></h1>
<main>{''.join(cols)}</main></body></html>"""
    tmp = HTML_OUT.with_suffix(".tmp")
    tmp.write_text(page)
    os.replace(tmp, HTML_OUT)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("title"); a.add_argument("--status", default="todo", choices=KEYS)
    a.add_argument("--who"); a.add_argument("--branch"); a.add_argument("--note")
    for x in (a,):
        x.add_argument("--goal"); x.add_argument("--context"); x.add_argument("--ac", help="acceptance criteria, ';'-separated")
    m = sub.add_parser("move"); m.add_argument("id"); m.add_argument("status", choices=KEYS); m.add_argument("--note")
    n = sub.add_parser("note"); n.add_argument("id"); n.add_argument("text")
    s = sub.add_parser("set"); s.add_argument("id"); s.add_argument("--who"); s.add_argument("--branch"); s.add_argument("--title")
    s.add_argument("--goal"); s.add_argument("--context"); s.add_argument("--ac", help="acceptance criteria, ';'-separated")
    ls = sub.add_parser("list"); ls.add_argument("--status", choices=KEYS)
    sub.add_parser("render")
    args = p.parse_args()

    if args.cmd in ("list", "render"):
        with Board(write=False) as data:
            if args.cmd == "render":
                render(data); print(HTML_OUT); return
            for key, en, _ in COLUMNS:
                if args.status and key != args.status:
                    continue
                for t in (t for t in data["tickets"] if t["status"] == key):
                    print(f'{t["id"]:6} {key:7} {t.get("who") or "-":16} {t["title"]}' + (f' — {t["note"]}' if t.get("note") else ""))
        return

    with Board(write=True) as data:
        if args.cmd == "add":
            t = {"id": f'T-{data["next_id"]}', "title": args.title, "status": args.status, "who": args.who,
                 "branch": args.branch, "note": args.note, "goal": args.goal, "context": args.context,
                 "ac": split_ac(args.ac), "created": now(), "updated": now(),
                 "history": [[now(), args.status]]}
            data["next_id"] += 1
            data["tickets"].append(t)
            print(t["id"])
            return
        t = find(data, args.id)
        if args.cmd == "move":
            t["status"] = args.status
            t.setdefault("history", []).append([now(), args.status])
            if args.note:
                t["note"] = args.note
        elif args.cmd == "note":
            t["note"] = args.text
        elif args.cmd == "set":
            for k in ("who", "branch", "title", "goal", "context"):
                if getattr(args, k):
                    t[k] = getattr(args, k)
            if args.ac:
                t["ac"] = split_ac(args.ac)
        t["updated"] = now()
        print(f'{t["id"]} -> {t["status"]}')


if __name__ == "__main__":
    main()
