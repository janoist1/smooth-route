#!/usr/bin/env python3
"""Static type check of backend/app (pyright, basic mode) against a baseline.

The code base predates type checking, so existing errors are recorded per
(file, rule) in pyright_baseline.json (the counted TODO list). The check fails
only when a (file, rule) bucket gets MORE errors than recorded, i.e. new code
must type-check. Fix errors freely; then lower the baseline with --update.

  python scripts/check_types.py            # check (CI)
  python scripts/check_types.py --update   # rewrite the baseline after fixing errors

Needs pyright (CI: `pip install pyright==1.1.389`; locally the same pip package or
`npx pyright@1.1.389`). Heavy third-party packages are stubbed as Any in
typings/, so the result is the same with or without torch installed.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(BACKEND, "pyright_baseline.json")
VERSION = "1.1.389"


def pyright_cmd():
    if shutil.which("pyright"):
        return ["pyright"]
    if shutil.which("npx"):
        return ["npx", "--yes", f"pyright@{VERSION}"]
    sys.exit(f"pyright not found: pip install pyright=={VERSION}")


def run_pyright():
    out = subprocess.run(pyright_cmd() + ["--outputjson", "--pythonpath", sys.executable],
                         cwd=BACKEND, capture_output=True, text=True)
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        sys.exit(f"pyright did not produce JSON:\n{out.stdout[-2000:]}\n{out.stderr[-2000:]}")
    errors = [d for d in data["generalDiagnostics"] if d["severity"] == "error"]
    for d in errors:
        d["file"] = os.path.relpath(d["file"], BACKEND)
    return errors


def buckets(errors):
    return Counter(f"{d['file']}::{d.get('rule', 'error')}" for d in errors)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = ap.parse_args(argv)
    errors = run_pyright()
    now = buckets(errors)
    if args.update:
        with open(BASELINE, "w") as f:
            json.dump({"pyright": VERSION, "total": sum(now.values()),
                       "errors": dict(sorted(now.items()))}, f, indent=1)
            f.write("\n")
        print(f"baseline written: {sum(now.values())} errors in {len(now)} (file, rule) buckets")
        return 0
    base = Counter(json.load(open(BASELINE))["errors"]) if os.path.exists(BASELINE) else Counter()
    worse = {k: (now[k], base.get(k, 0)) for k in now if now[k] > base.get(k, 0)}
    better = sum(max(0, base[k] - now.get(k, 0)) for k in base)
    if worse:
        print("New type errors (pyright basic) — fix them, do not raise the baseline:")
        for d in errors:
            k = f"{d['file']}::{d.get('rule', 'error')}"
            if k in worse:
                line = d["range"]["start"]["line"] + 1
                print(f"  {d['file']}:{line}: {d.get('rule')}: {d['message'].splitlines()[0]}")
        for k, (n, b) in sorted(worse.items()):
            print(f"  [{k}] {n} > baseline {b}")
        return 1
    msg = f"type check OK: {sum(now.values())} known errors (baseline {sum(base.values())})"
    if better:
        msg += f"; {better} fixed — lower the baseline: python scripts/check_types.py --update"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
