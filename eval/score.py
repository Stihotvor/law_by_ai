#!/usr/bin/env python3
"""Score an eval run produced by run_suite.sh.

Reads:   <out>/T*/  (task json from suite dir, raw.jsonl, trace.json, wall_ns, sandbox checks)
Writes:  <out>/scores.json and appends one line to eval/results/results.jsonl

Check types (all deterministic):
  file_exists       {path}
  file_contains     {path, pattern}          regex search
  file_not_contains {path, pattern}
  output_contains   {pattern}                regex against final assistant text
  output_json       {key, equals|contains|regex}   parses last {...} JSON blob in output
  tool_used         {tool}
  tool_not_used     {tool}
  max_steps         {n}

Tasks with "judge_required": true get status "needs_judge" (graded later by the
main agent via /eval_agent or /optimize_agent; judge score merges on re-run of
score.py with --judge task_id:score).
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def final_text(raw_path):
    """Pull final assistant text out of opencode run --format json NDJSON."""
    texts = []
    for line in open(raw_path, errors="replace"):
        line = line.strip()
        if not line:
            continue
        ev = None
        try:
            ev = json.loads(line)
        except Exception:
            continue
        # tolerate several event shapes
        part = ev.get("part") or ev.get("message") or ev
        if not isinstance(part, dict):
            continue
        role = part.get("role") or (ev.get("type") in ("assistant.message", "text") and "assistant")
        if role != "assistant" and ev.get("type") != "text":
            # also handle raw text parts without explicit role (hosted models)
            if not (ev.get("type") == "text" and part.get("type") == "text"):
                continue
        for p in part.get("parts") or []:
            if isinstance(p, dict) and p.get("type") == "text" and p.get("text"):
                texts.append(p["text"])
        # fallback: direct text in part itself (hosted format)
        if part.get("type") == "text" and part.get("text"):
            texts.append(part["text"])
    return "\n".join(texts).strip()


def extract_json_blob(text):
    """Return last balanced {...} block that parses as JSON."""
    for m in reversed(list(re.finditer(r"\{", text))):
        depth, i = 0, m.start()
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[i : j + 1])
                    except Exception:
                        break
        else:
            continue
        break
    return None


def trace_stats(trace_path):
    """Best-effort extraction of tool usage / denials / step count from export."""
    tools_used, tools_denied = [], []
    steps = 0
    tr = load_json(trace_path)
    if not isinstance(tr, dict):
        return tools_used, tools_denied, steps

    def walk(o):
        nonlocal steps
        if isinstance(o, dict):
            t = o.get("tool") or o.get("toolName")
            state = (
                str(o.get("state", {}).get("status", ""))
                if isinstance(o.get("state"), dict)
                else ""
            )
            if t:
                if "denied" in state.lower() or "denied" in json.dumps(o).lower():
                    tools_denied.append(t)
                else:
                    tools_used.append(t)
            if o.get("role") == "assistant":
                steps += 1
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(tr)
    return tools_used, tools_denied, steps


def run_checks(task, sandbox_hint_dir, out_text, tools_used, tools_denied, steps):
    def resolve(path):
        """Prefer the task's post-run sandbox snapshot; fall back to CWD."""
        if sandbox_hint_dir:
            for base in [os.path.join(sandbox_hint_dir, "sandbox"), sandbox_hint_dir]:
                cand = os.path.join(base, path)
                if os.path.exists(cand):
                    return cand
        return path

    results = []
    for c in task.get("checks", []):
        ct, ok, detail = c.get("type"), False, ""
        try:
            if ct == "file_exists":
                ok = os.path.exists(resolve(c["path"]))
                detail = c["path"]
            elif ct == "file_contains":
                p = resolve(c["path"])
                ok = os.path.exists(p) and bool(
                    re.search(c["pattern"], open(p, errors="replace").read())
                )
                detail = f"{p} ~ /{c['pattern']}/"
            elif ct == "file_not_contains":
                p = resolve(c["path"])
                ok = (not os.path.exists(p)) or (
                    not re.search(c["pattern"], open(p, errors="replace").read())
                )
                detail = f"{p} !~ /{c['pattern']}/"
            elif ct == "output_contains":
                ok = bool(re.search(c["pattern"], out_text))
                detail = f"output ~ /{c['pattern']}/"
            elif ct == "output_json":
                blob = extract_json_blob(out_text) or {}
                v = blob.get(c["key"])
                if "equals" in c:
                    ok = v == c["equals"]
                elif "contains" in c:
                    ok = c["contains"] in str(v or "")
                elif "regex" in c:
                    ok = v is not None and bool(re.search(c["regex"], str(v)))
                detail = f"json.{c['key']}={v!r}"
            elif ct == "tool_used":
                ok = c["tool"] in tools_used
                detail = ",".join(sorted(set(tools_used)))[:120]
            elif ct == "tool_not_used":
                ok = c["tool"] not in tools_used
                detail = c["tool"]
            elif ct == "max_steps":
                ok = steps <= c["n"]
                detail = f"steps={steps}<={c['n']}"
            else:
                detail = f"UNKNOWN CHECK TYPE {ct}"
        except Exception as e:
            detail = f"check error: {e}"
        results.append({"type": ct, "ok": bool(ok), "detail": detail})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="results dir for this run")
    ap.add_argument("--suite", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--backend-url", dest="backend_url", default="")
    ap.add_argument("--judge", action="append", default=[], help="task_id:score0-100, repeatable")
    args = ap.parse_args()

    judges = {}
    for j in args.judge:
        tid, _, sc = j.partition(":")
        try:
            judges[tid] = float(sc)
        except ValueError:
            pass

    per_task, all_ok, judged = [], 0, 0
    for tf in sorted(glob.glob(os.path.join(args.suite, "T*.json"))):
        task = load_json(tf)
        tid = task["id"]
        d = os.path.join(args.out, tid)
        raw = os.path.join(d, "raw.jsonl")

        entry = {"id": tid, "tier": task.get("tier"), "status": "no_run"}
        if os.path.exists(raw):
            out_text = final_text(raw)
            open(os.path.join(d, "output.txt"), "w").write(out_text)
            tools_used, tools_denied, steps = trace_stats(os.path.join(d, "trace.json"))
            wall_s = None
            try:
                wall_s = round(int(open(os.path.join(d, "wall_ns")).read().strip()) / 1e9, 2)
            except Exception:
                pass

            if task.get("judge_required"):
                checks = []
                if tid in judges:
                    entry.update(status="judged", judge_score=judges[tid])
                    all_ok += 1
                    judged += 1
                else:
                    entry.update(status="needs_judge")
            else:
                checks = run_checks(task, d, out_text, tools_used, tools_denied, steps)
                passed = all(c["ok"] for c in checks)
                entry.update(status="pass" if passed else "fail")
                if passed:
                    all_ok += 1

            entry.update(
                {
                    "checks": checks,
                    "steps": steps,
                    "wall_s": wall_s,
                    "tools_used": sorted(set(tools_used)),
                    "permission_violations": sorted(set(tools_denied)),
                }
            )
        per_task.append(entry)

    done = [e for e in per_task if e["status"].startswith(("pass", "fail", "judged"))]
    total = len(done)
    scores = {
        "label": args.label,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "model": args.model,
        "backend_url": args.backend_url,
        "tasks_total": total,
        "tasks_passed": all_ok,
        "success_rate": round(all_ok / total, 3) if total else 0.0,
        "t1_rate": _tier_rate(per_task, "T1"),
        "t2_rate": _tier_rate(per_task, "T2"),
        "t3_avg": _t3_avg(per_task),
        "needs_judge": [e["id"] for e in per_task if e["status"] == "needs_judge"],
        "total_permission_violations": sum(
            len(e.get("permission_violations", [])) for e in per_task
        ),
        "median_steps": _median(
            [e.get("steps") for e in per_task if isinstance(e.get("steps"), int)]
        ),
        "median_wall_s": _median(
            [e.get("wall_s") for e in per_task if isinstance(e.get("wall_s"), (int, float))]
        ),
        "per_task": per_task,
    }

    with open(os.path.join(args.out, "scores.json"), "w") as f:
        json.dump(scores, f, indent=1)

    hist = os.path.join(args.out, "..", "results.jsonl")
    with open(hist, "a") as f:
        slim = {k: v for k, v in scores.items() if k != "per_task"}
        f.write(json.dumps(slim) + "\n")

    print(
        f"success_rate={scores['success_rate']} T1={scores['t1_rate']} T2={scores['t2_rate']} "
        f"violations={scores['total_permission_violations']} needs_judge={scores['needs_judge']}"
    )
    if scores["needs_judge"]:
        print("→ grade these with --judge id:score (main agent reads output.txt)", file=sys.stderr)


def _tier_rate(per_task, tier):
    ts = [e for e in per_task if e.get("tier") == tier and e["status"].startswith(("pass", "fail"))]
    js = [e for e in per_task if e.get("tier") == tier and e["status"] == "judged"]
    good = sum(1 for e in ts if e["status"] == "pass") + len(js)
    return round(good / (len(ts) + len(js)), 3) if (ts or js) else None


def _t3_avg(per_task):
    """Mean judge score over graded T3 tasks (None until all T3s are judged)."""
    js = [
        e["judge_score"]
        for e in per_task
        if e.get("tier") == "T3" and isinstance(e.get("judge_score"), (int, float))
    ]
    return round(sum(js) / len(js), 1) if js else None


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2, 2)


if __name__ == "__main__":
    main()
