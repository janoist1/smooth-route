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
    python3 tools/board.py decide T-7 "what we chose and why, in plain words"
    python3 tools/board.py set T-7 --who qa --branch claude/x --title "…" \
        --goal "why" --context "background" --ac "criterion 1; criterion 2"
    python3 tools/board.py work T-7 --who codex --model gpt-6.1-sol --effort xhigh --codex-session <id>
    python3 tools/board.py ask T-7 --question "…" --option "A::why" --option "B::why" --recommended 1
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


def fmt_tokens(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def ticket_tokens(t) -> dict:
    tot = {"uncached": 0, "cached": 0, "write": 0, "output": 0, "total_only": 0}
    for w in t.get("workers") or []:
        for k in tot:
            tot[k] += int((w.get("tokens") or {}).get(k) or 0)
    return tot


def render(data) -> None:
    def card(t):
        workers = t.get("workers") or []
        bits = []
        if workers:
            names = []
            for w in workers:
                name = " ".join(x for x in ((w.get("who") or "").split(" (")[0], w.get("effort")) if x)
                if name and name not in names:
                    names.append(name)
            bits.append(" + ".join(names))
        elif t.get("who"):
            bits.append(t["who"])
        tok = ticket_tokens(t)
        total = tok["uncached"] + tok["cached"] + tok["write"] + tok["output"] + tok["total_only"]
        if total:
            share = (tok["cached"] / (tok["uncached"] + tok["cached"] + tok["write"])
                     if (tok["uncached"] + tok["cached"] + tok["write"]) else 0)
            bits.append(f"{fmt_tokens(total)} tok" + (f" ({share:.0%} cache)" if share else ""))
        meta = " · ".join(html.escape(b) for b in bits if b)
        note = f'<p class="note">{html.escape(t["note"])}</p>' if t.get("note") else ""
        pill = '<span class="pill">kérdés vár</span>' if t.get("ask") and t["status"] == "owner" else ""
        return (f'<article class="card" data-id="{t["id"]}" tabindex="0" role="button">'
                f'<header><b>{t["id"]}</b><time>{t["updated"]}</time></header>'
                f'<h3>{html.escape(t["title"])}</h3>{pill}{note}'
                f'{f"<footer>{meta}</footer>" if meta else ""}</article>')

    cols = []
    for key, en, hu in COLUMNS:
        items = [t for t in data["tickets"] if t["status"] == key]
        items.sort(key=lambda t: t["updated"], reverse=True)
        if key == "done":
            items = items[:40]
        cols.append(f'<section class="col {key}"><h2>{en} <span>· {hu}</span><em>{len(items)}</em></h2>'
                    f'<div class="list" data-col="{key}">' + "".join(card(t) for t in items) + "</div></section>")
    keep = ("id", "title", "status", "who", "branch", "note", "goal", "context", "ac", "decisions",
            "workers", "ask", "history", "created", "updated")
    payload = json.dumps({t["id"]: {k: t.get(k) for k in keep} for t in data["tickets"]},
                         ensure_ascii=False).replace("</", "<\\/")
    # Trello-like: the page never scrolls; columns scroll sideways on narrow
    # screens and each column's cards scroll on their own. A card opens its
    # details in a modal. Refresh every 60 s, keeping scroll and the open card.
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Team board</title><style>
:root{{--bg:#f6f7f9;--fg:#1d2330;--muted:#667085;--card:#fff;--line:#e3e6ec;--colbg:#eceff3;--accent:#2563eb;--todo:#94a3b8;--doing:#3b82f6;--review:#a855f7;--owner:#f59e0b;--done:#22c55e;--rec:#e8f0fe}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151b;--fg:#e6e9ef;--muted:#98a2b3;--card:#1c2129;--line:#2a313c;--colbg:#181c23;--accent:#7aa2f7;--rec:#1b2a44}}}}
*{{box-sizing:border-box}}html,body{{height:100%}}
body{{margin:0;padding:16px 16px 12px;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,-apple-system,sans-serif;height:100vh;height:100dvh;display:flex;flex-direction:column;overflow:hidden}}
h1{{flex:none;font-size:18px;margin:0 0 12px}}h1 small{{color:var(--muted);font-weight:400;font-size:13px}}
main{{flex:1;min-height:0;display:grid;grid-template-columns:repeat(5,minmax(240px,1fr));gap:12px;align-items:stretch;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;touch-action:pan-x pan-y}}
@media (max-width:900px){{main{{grid-template-columns:repeat(5,minmax(78vw,1fr));scroll-snap-type:x proximity}}.col{{scroll-snap-align:start}}}}
.col{{display:flex;flex-direction:column;min-height:0;background:var(--colbg);border-top:4px solid var(--line);border-radius:8px;padding:8px 8px 0}}
.list{{flex:1;min-height:0;overflow-x:hidden;overflow-y:auto;overscroll-behavior-y:contain;padding-bottom:8px}}
.col h2{{flex:none;font-size:13px;text-transform:uppercase;letter-spacing:.04em;margin:0 0 8px;display:flex;gap:6px;align-items:baseline}}
.col h2 span{{color:var(--muted);text-transform:none;letter-spacing:0;font-weight:400}}.col h2 em{{margin-left:auto;font-style:normal;color:var(--muted)}}
.todo{{border-color:var(--todo)}}.doing{{border-color:var(--doing)}}.review{{border-color:var(--review)}}.owner{{border-color:var(--owner)}}.done{{border-color:var(--done)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin-bottom:8px;cursor:pointer}}
.card:hover,.card:focus-visible{{border-color:var(--accent);outline:none}}
.card header{{display:flex;justify-content:space-between;color:var(--muted);font-size:12px}}
.card h3{{font-size:14px;margin:4px 0}}.note{{margin:4px 0;color:var(--muted);font-size:13px}}
.card footer{{font-size:12px;color:var(--muted);word-break:break-word}}.owner .card{{border-color:var(--owner)}}
.pill{{display:inline-block;font-size:11px;font-weight:600;padding:1px 7px;border-radius:999px;background:var(--owner);color:#1d1400}}
dialog{{border:1px solid var(--line);border-radius:12px;padding:0;width:min(640px,94vw);max-height:86vh;background:var(--card);color:var(--fg)}}
dialog::backdrop{{background:rgba(10,14,20,.45)}}
.dlg{{display:flex;flex-direction:column;max-height:86vh}}
.dlg-head{{display:flex;gap:8px;align-items:flex-start;padding:14px 16px 8px;border-bottom:1px solid var(--line)}}
.dlg-head h2{{font-size:16px;margin:0;flex:1}}.dlg-head small{{display:block;color:var(--muted);font-weight:400;font-size:12px;margin-top:2px}}
.dlg-head button{{border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:8px;padding:4px 10px;font:inherit;cursor:pointer}}
.dlg-body{{padding:8px 16px 16px;overflow-y:auto}}
.dlg-body h4{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:14px 0 4px}}
.dlg-body p,.dlg-body ul{{margin:4px 0}}.dlg-body ul{{padding-left:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:4px 6px;border-bottom:1px solid var(--line);white-space:nowrap}}td.n,th.n{{text-align:right}}
.tbl{{overflow-x:auto}}
.opt{{border:1px solid var(--line);border-radius:8px;padding:6px 8px;margin:6px 0}}.opt.rec{{border-color:var(--accent);background:var(--rec)}}
.opt b{{display:block}}.opt span{{color:var(--muted);font-size:13px}}
</style></head><body><h1>Team board <small>updated {now()} · auto-refresh 1 min · tap a card for details</small></h1>
<main>{''.join(cols)}</main>
<dialog id="dlg"><div class="dlg"><div class="dlg-head"><h2 id="dlg-title"></h2><button type="button" id="dlg-close">Bezár</button></div><div class="dlg-body" id="dlg-body"></div></div></dialog>
<script id="tickets" type="application/json">{payload}</script>
<script>
(function(){{
  var T=JSON.parse(document.getElementById("tickets").textContent);
  var dlg=document.getElementById("dlg"), body=document.getElementById("dlg-body"), title=document.getElementById("dlg-title");
  var openId=null, KEY="board-view";
  function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
  function fmt(n){{n=+n||0;return n>=1e6?(n/1e6).toFixed(2)+"M":n>=1e3?Math.round(n/1e3)+"k":String(n)}}
  function sec(h,inner){{return inner?"<h4>"+h+"</h4>"+inner:""}}
  function list(a,f){{return a&&a.length?"<ul>"+a.map(f).join("")+"</ul>":""}}
  function show(id){{
    var t=T[id]; if(!t) return; openId=id;
    title.innerHTML=esc(t.id+" · "+t.title)+"<small>"+esc([t.status,t.who,t.branch].filter(Boolean).join(" · "))+" · updated "+esc(t.updated)+"</small>";
    var h="";
    if(t.note) h+=sec("Note","<p>"+esc(t.note)+"</p>");
    if(t.ask){{
      var a=t.ask, o=(a.options||[]).map(function(x,i){{return '<div class="opt'+(i+1===a.recommended?' rec':'')+'"><b>'+esc(x.label)+(i+1===a.recommended?' (javasolt)':'')+'</b><span>'+esc(x.description||"")+'</span></div>'}}).join("");
      h+=sec("Kérdés neked","<p>"+esc(a.question)+"</p>"+o+(a.why?"<p><i>"+esc(a.why)+"</i></p>":""));
    }}
    if(t.goal) h+=sec("Goal","<p>"+esc(t.goal)+"</p>");
    if(t.context) h+=sec("Context","<p>"+esc(t.context)+"</p>");
    h+=sec("Done when",list(t.ac,function(x){{return "<li>"+esc(x)+"</li>"}}));
    h+=sec("Decisions",list(t.decisions,function(x){{return "<li>"+esc(x[1])+" <small>("+esc(x[0])+")</small></li>"}}));
    var w=t.workers||[];
    if(w.length){{
      var rows=w.map(function(x){{var k=x.tokens||{{}};var tot=(+k.uncached||0)+(+k.cached||0)+(+k.write||0)+(+k.output||0)+(+k.total_only||0);
        return "<tr><td>"+esc(x.who)+"</td><td>"+esc(x.model||"")+"</td><td>"+esc(x.effort||"")+"</td><td class=n>"+(k.total_only||!tot?"–":fmt(k.uncached))+"</td><td class=n>"+(k.total_only||!tot?"–":fmt(k.cached))+"</td><td class=n>"+(k.total_only||!tot?"–":fmt(k.output))+"</td><td class=n>"+(tot?fmt(tot):"–")+"</td></tr>"
        +(x.note?"<tr><td colspan=7><small>"+esc(x.note)+"</small></td></tr>":"")}}).join("");
      h+=sec("Who worked on it","<div class=tbl><table><tr><th>Who</th><th>Model</th><th>Effort</th><th class=n>Input</th><th class=n>Cached</th><th class=n>Output</th><th class=n>Total</th></tr>"+rows+"</table></div><p><small>Input = not cached. Codex input includes reasoning context; '–' = only a total was logged.</small></p>");
    }}
    h+=sec("History",list(t.history,function(x){{return "<li>"+esc(x[0])+" → "+esc(x[1])+"</li>"}}));
    body.innerHTML=h; body.scrollTop=0;
    if(!dlg.open) dlg.showModal();
  }}
  document.querySelectorAll("article.card").forEach(function(a){{
    a.addEventListener("click",function(){{show(a.dataset.id)}});
    a.addEventListener("keydown",function(e){{if(e.key==="Enter"||e.key===" "){{e.preventDefault();show(a.dataset.id)}}}});
  }});
  document.getElementById("dlg-close").addEventListener("click",function(){{dlg.close()}});
  dlg.addEventListener("click",function(e){{if(e.target===dlg)dlg.close()}});
  dlg.addEventListener("close",function(){{openId=null}});
  function save(){{try{{
    var s={{x:document.querySelector("main").scrollLeft,lists:{{}},open:openId}};
    document.querySelectorAll(".list").forEach(function(l){{s.lists[l.dataset.col]=l.scrollTop}});
    sessionStorage.setItem(KEY,JSON.stringify(s));
  }}catch(e){{}}}}
  try{{
    var s=JSON.parse(sessionStorage.getItem(KEY)||"null");
    if(s){{
      document.querySelector("main").scrollLeft=s.x||0;
      document.querySelectorAll(".list").forEach(function(l){{l.scrollTop=(s.lists||{{}})[l.dataset.col]||0}});
      if(s.open) show(s.open);
    }}
  }}catch(e){{}}
  setTimeout(function(){{save();location.reload()}},60000);
  window.addEventListener("pagehide",save);
}})();
</script></body></html>"""
    tmp = HTML_OUT.with_suffix(".tmp")
    tmp.write_text(page)
    os.replace(tmp, HTML_OUT)


# --- token usage --------------------------------------------------------------
# Normalised per worker: uncached input, cached input read, cache write, output;
# total_only when a log only gives one number (e.g. ephemeral codex runs).

def codex_usage(session_id: str) -> dict:
    """Last cumulative token_count of a Codex rollout (~/.codex/sessions)."""
    files = list(Path.home().glob(f".codex/sessions/**/rollout-*{session_id}.jsonl"))
    if not files:
        sys.exit(f"no codex rollout for session {session_id}")
    last = None
    for line in files[0].read_text().splitlines():
        if '"token_count"' in line:
            info = (json.loads(line).get("payload") or {}).get("info") or {}
            last = info.get("total_token_usage") or last
    if not last:
        return {}
    cached = int(last.get("cached_input_tokens") or 0)
    return {"uncached": int(last.get("input_tokens") or 0) - cached, "cached": cached,
            "write": int(last.get("cache_write_input_tokens") or 0),
            "output": int(last.get("output_tokens") or 0)}


def codex_log_total(path: str) -> int:
    """Sum of the 'tokens used' totals printed by `codex exec` in a log."""
    lines = Path(path).read_text().splitlines()
    total = 0
    for i, line in enumerate(lines[:-1]):
        digits = "".join(ch for ch in lines[i + 1] if ch.isdigit())  # "35 816" uses a narrow space
        if line.strip() == "tokens used" and digits:
            total += int(digits)
    return total


def claude_usage(transcript: str, since: str | None = None, until: str | None = None) -> dict:
    """Sum assistant usage in a Claude Code transcript (+ its subagents), optionally
    limited to a local-time window 'YYYY-MM-DD HH:MM'."""
    from datetime import timezone
    lo = datetime.strptime(since, "%Y-%m-%d %H:%M").astimezone(timezone.utc) if since else None
    hi = datetime.strptime(until, "%Y-%m-%d %H:%M").astimezone(timezone.utc) if until else None
    root = Path(transcript)
    files = [root] + sorted((root.parent / root.stem / "subagents").glob("*.jsonl"))
    seen, tot = set(), {"uncached": 0, "cached": 0, "write": 0, "output": 0}
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if '"usage"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            msg = e.get("message") or {}
            u = msg.get("usage")
            if not u or (msg.get("id"), f.name) in seen:
                continue
            ts = e.get("timestamp")
            if ts and (lo or hi):
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if (lo and t < lo) or (hi and t > hi):
                    continue
            seen.add((msg.get("id"), f.name))
            tot["uncached"] += int(u.get("input_tokens") or 0)
            tot["cached"] += int(u.get("cache_read_input_tokens") or 0)
            tot["write"] += int(u.get("cache_creation_input_tokens") or 0)
            tot["output"] += int(u.get("output_tokens") or 0)
    return tot


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("title"); a.add_argument("--status", default="todo", choices=KEYS)
    a.add_argument("--who"); a.add_argument("--branch"); a.add_argument("--note")
    for x in (a,):
        x.add_argument("--goal"); x.add_argument("--context"); x.add_argument("--ac", help="acceptance criteria, ';'-separated")
    m = sub.add_parser("move"); m.add_argument("id"); m.add_argument("status", choices=KEYS); m.add_argument("--note")
    n = sub.add_parser("note"); n.add_argument("id"); n.add_argument("text")
    dc = sub.add_parser("decide", help="record a decision (plain language: what + why)")
    dc.add_argument("id"); dc.add_argument("text")
    s = sub.add_parser("set"); s.add_argument("id"); s.add_argument("--who"); s.add_argument("--branch"); s.add_argument("--title")
    s.add_argument("--goal"); s.add_argument("--context"); s.add_argument("--ac", help="acceptance criteria, ';'-separated")
    w = sub.add_parser("work", help="record who worked on a ticket (model, effort, tokens)")
    w.add_argument("id"); w.add_argument("--who", required=True); w.add_argument("--model"); w.add_argument("--effort")
    w.add_argument("--note")
    for k in ("uncached", "cached", "write", "output", "total"):
        w.add_argument(f"--{k}", type=int, default=0)
    w.add_argument("--codex-session", action="append", default=[], help="sum a Codex rollout's tokens")
    w.add_argument("--codex-log", action="append", default=[], help="sum 'tokens used' totals of a codex exec log")
    w.add_argument("--claude-transcript", help="sum a Claude Code transcript's usage (+ subagents)")
    w.add_argument("--since", help="'YYYY-MM-DD HH:MM' local, with --claude-transcript")
    w.add_argument("--until", help="'YYYY-MM-DD HH:MM' local, with --claude-transcript")
    q = sub.add_parser("ask", help="store the owner question with options + recommendation")
    q.add_argument("id"); q.add_argument("--question", required=True)
    q.add_argument("--option", action="append", default=[], help="'label::description' (repeat, 2-4)")
    q.add_argument("--recommended", type=int, default=1, help="1-based index of the recommended option")
    q.add_argument("--why", help="one line: why the recommendation")
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
            print("tip: record major decisions in plain language: board.py decide T-<n> \"what we chose + why\"")
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
        elif args.cmd == "work":
            tok = {"uncached": args.uncached, "cached": args.cached, "write": args.write,
                   "output": args.output, "total_only": args.total}
            for sid in args.codex_session:
                for k, v in codex_usage(sid).items():
                    tok[k] += v
            for log in args.codex_log:
                tok["total_only"] += codex_log_total(log)
            if args.claude_transcript:
                for k, v in claude_usage(args.claude_transcript, args.since, args.until).items():
                    tok[k] += v
            t.setdefault("workers", []).append({"who": args.who, "model": args.model, "effort": args.effort,
                                                "note": args.note, "at": now(),
                                                "tokens": {k: v for k, v in tok.items() if v}})
        elif args.cmd == "ask":
            opts = []
            for o in args.option:
                label, _, desc = o.partition("::")
                opts.append({"label": label.strip(), "description": desc.strip()})
            t["ask"] = {"question": args.question, "options": opts, "recommended": args.recommended,
                        "why": args.why}
        elif args.cmd == "decide":
            t.setdefault("decisions", []).append([now(), args.text])
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
