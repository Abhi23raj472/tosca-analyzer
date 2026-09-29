"""Requirement check: line up the manual steps from a ticket with a Tosca test case.

The alignment is order-preserving: each Tosca step is either assigned to one
expected step (never going backwards) or left over as an "extra" step. The
best assignment is found with a small dynamic programme over word overlap.
"""
from __future__ import annotations

import math
import re

STOP = {
    "a", "an", "the", "is", "are", "be", "been", "to", "of", "in", "on", "at", "as", "and", "or", "with", "for",
    "should", "must", "will", "can", "it", "its", "this", "that", "then", "into", "from", "by", "user", "value",
    "values", "input", "verify", "waiton", "actionmode", "true", "false", "click", "step", "expect", "expected",
    "cp", "xl", "pl", "tds", "tcp", "rtb", "tbox", "module", "contain",
}
SYNONYMS = {
    "signin": "login", "logon": "login", "log": "login", "sign": "login", "authenticate": "login",
    "dx": "diagnosis", "amt": "amount", "attach": "upload", "attachment": "upload", "document": "upload",
    "file": "upload", "doc": "upload", "confirmation": "confirm", "confirmed": "confirm", "submitted": "submit",
    "populate": "fill", "prefill": "fill", "autofill": "fill", "display": "show", "displayed": "show", "shown": "show",
    "visible": "show", "open": "open", "new": "new", "create": "new", "status": "status", "state": "status",
}
QUOTED = re.compile(r"[\"“”']([^\"“”']{2,})[\"“”']")
IS_VALUE = re.compile(r"\b(?:is|equals|shows|should be|becomes|reads)\s+([A-Z][\w ]{1,40})\s*\.?$")
SKIP_SCORE = 0.16  # below this similarity a Tosca step is better left unassigned


def tokens(text: str) -> set[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    out = set()
    for w in re.findall(r"[A-Za-z0-9]+", text.lower()):
        if w in STOP or len(w) < 2:
            continue
        w = SYNONYMS.get(w, w)
        for suf in ("ing", "ed", "es", "s"):
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.add(SYNONYMS.get(w, w))
    return out - STOP


def similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return 0.6 * inter / min(len(a), len(b)) + 0.4 * 2 * inter / (len(a) + len(b))


def _is_click(v: dict) -> bool:
    return (v.get("value") or "").strip().lower() in {"{click}", "click", "x", "{leftclick}", "{doubleclick}"}


def render_step(step: dict) -> list[str]:
    if step.get("kind") == "reference":
        params = ", ".join(f"{{{v['name']}}}" if not v.get("value") or v["value"].startswith("{") else f"{v['name']}={v['value']}"
                           for v in step.get("values", []))
        return [f"{step.get('reference') or step['name']} {params}".strip()]
    lines = []
    tbox = re.match(r"tbox", step.get("module") or step.get("name") or "", re.I)
    for v in step.get("values", []):
        label = (step["name"] + " · " if tbox else "") + v["name"]
        mode = v.get("action_mode") or "Input"
        if _is_click(v):
            lines.append(f"{label}  ({mode}: Click)")
        else:
            val = v.get("value") or ""
            shown = val if val.startswith("{") or val.replace(".", "").isdigit() else f'"{val}"'
            lines.append(f"{label} = {shown}  ({mode})")
    return lines or [step["name"]]


def _step_text(step: dict) -> str:
    parts = [step.get("name", ""), step.get("module", ""), step.get("reference") or ""]
    for v in step.get("values", []):
        parts += [v["name"], v.get("value", "") if not (v.get("value") or "").startswith("{") else v["value"].strip("{}")]
    return " ".join(p for p in parts if p)


def _step_tokens(step: dict) -> tuple[dict[str, float], set[str]]:
    """Weighted tokens for a Tosca step. Values and references say more than the module name,
    which is often shared by many steps on the same screen."""
    weights: dict[str, float] = {}
    for t in tokens(" ".join([step.get("name", ""), step.get("module", "")])):
        weights[t] = max(weights.get(t, 0), 0.5)
    for t in tokens(step.get("reference") or ""):
        weights[t] = 1.0
    checks: set[str] = set()
    for v in step.get("values", []):
        val = v.get("value") or ""
        for t in tokens(v["name"] + " " + (val.strip("{}") if val.startswith("{") else val)):
            weights[t] = 1.0
        if (v.get("action_mode") or "").lower() in {"verify", "waiton"}:
            checks |= tokens(v["name"])
    return weights, checks


def _weighted_sim(a: dict[str, float], b: set[str], idf: dict[str, float], default: float) -> float:
    if not a or not b:
        return 0.0
    wa = sum(idf.get(t, default) * m for t, m in a.items())
    wb = sum(idf.get(t, default) for t in b)
    inter = sum(idf.get(t, default) * m for t, m in a.items() if t in b)
    return 0.6 * inter / min(wa, wb) + 0.4 * 2 * inter / (wa + wb)


def _expected_value(expected: str) -> str | None:
    m = QUOTED.search(expected or "")
    if m:
        return m.group(1).strip()
    m = IS_VALUE.search((expected or "").strip())
    return m.group(1).strip() if m else None


def align(expected: list[dict], steps: list[dict]) -> list[int | None]:
    """Return, for each Tosca step, the index of the expected step it implements (or None)."""
    n, m = len(expected), len(steps)
    if n == 0:
        return [None] * m
    etok = [tokens(e.get("action", "") + " " + e.get("expected", "")) for e in expected]
    exp_only = [tokens(e.get("expected", "")) for e in expected]
    df: dict[str, int] = {}
    for toks in etok:
        for t in toks:
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log(1 + n / c) for t, c in df.items()}
    default = math.log(1 + n)
    sim = []
    for s in steps:
        weights, checks = _step_tokens(s)
        row = []
        for j in range(n):
            base = _weighted_sim(weights, etok[j], idf, default)
            if checks and exp_only[j]:
                wc = sum(idf.get(t, default) for t in checks) or 1
                base += 0.3 * sum(idf.get(t, default) for t in checks & exp_only[j]) / wc
            row.append(base)
        sim.append(row)
    NEG = -1e9
    f = [0.0] * n  # f[j]: best score so far with the last assignment <= j
    back: list[list[tuple[int | None, int]]] = []
    for t in range(m):
        new = [NEG] * n
        choice: list[tuple[int | None, int]] = [(None, 0)] * n
        for j in range(n):
            skip, take = f[j] + SKIP_SCORE, f[j] + sim[t][j]
            new[j], choice[j] = (take, (j, j)) if take > skip and sim[t][j] >= SKIP_SCORE else (skip, (None, j))
        for j in range(1, n):  # prefix max so the next step may assign to any index >= this one
            if new[j - 1] > new[j]:
                new[j], choice[j] = new[j - 1], ("carry", j - 1)
        back.append(choice)
        f = new
    out: list[int | None] = [None] * m
    j = n - 1
    for t in range(m - 1, -1, -1):
        c, k = back[t][j]
        while c == "carry":
            j = k
            c, k = back[t][j]
        out[t] = c
        j = k
    return out


def check(expected: list[dict], steps: list[dict], acceptance: list[str] | None = None) -> dict:
    active_steps = [s for s in steps if not s.get("disabled")]
    assign = align(expected, active_steps)
    rows = []
    for j, e in enumerate(expected):
        mine = [s for s, a in zip(active_steps, assign) if a == j]
        exp_text = (e.get("expected") or "").strip()
        built = [line for s in mine for line in render_step(s)]
        row = {"n": j + 1, "action": e.get("action", ""), "expected": exp_text, "built": built,
               "tosca_steps": [s["index"] for s in mine], "status": "matched", "hint": ""}
        if not mine:
            row["status"] = "missing"
            what = e.get("action", "this step").rstrip(".")
            row["hint"] = (f"Add a step that does \"{what}\"" +
                           (f", then verify: {exp_text[0].lower() + exp_text[1:]}" if exp_text else "") + ".")
        elif exp_text:
            checks = [v for s in mine for v in s.get("values", [])
                      if (v.get("action_mode") or "").lower() in {"verify", "waiton"}]
            want = _expected_value(exp_text)
            etok = tokens(exp_text)
            related = [v for v in checks if tokens(v["name"]) & etok] or checks
            if not checks:
                row["status"] = "partial"
                row["hint"] = (f"The step runs the action but never checks that {exp_text[0].lower() + exp_text[1:].rstrip('.')}. "
                               "Add a WaitOn or Verify for it.")
            elif want and related and not any(want.lower() in (v.get("value") or "").lower() or
                                               (v.get("value") or "").startswith("{") for v in related):
                row["status"] = "mismatch"
                got = related[0].get("value") or "(empty)"
                row["hint"] = (f"The test verifies {related[0]['name'].split('.')[-1]} = \"{got}\" but the ticket expects "
                               f"\"{want}\". Change the verified value, or update the ticket if the requirement changed.")
        rows.append(row)

    extras = [s for s, a in zip(active_steps, assign) if a is None]
    for s in extras:
        rows.append({"n": None, "action": "Not in the ticket", "expected": "", "built": render_step(s),
                     "tosca_steps": [s["index"]], "status": "extra",
                     "hint": "This step is not in the ticket. Remove it, or ask the owner to add it to the expected steps."})

    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("matched", "partial", "mismatch", "missing", "extra")}

    criteria = []
    for ac in acceptance or []:
        atok = tokens(ac)
        scored = sorted(((similarity(atok, tokens(r["action"] + " " + r["expected"])), r) for r in rows if r["n"]),
                        key=lambda x: -x[0])
        best = [r for sc, r in scored[:2] if sc >= 0.25] or ([scored[0][1]] if scored else [])
        covered = bool(best) and all(r["status"] == "matched" for r in best[:1])
        criteria.append({"text": ac, "covered": covered, "steps": [r["n"] for r in best]})

    return {
        "rows": rows,
        "counts": counts,
        "expected_steps": len(expected),
        "design_match": counts["matched"],
        "criteria": criteria,
        "criteria_covered": sum(1 for c in criteria if c["covered"]),
    }


def comment_text(issue_key: str, test_case: str, result: dict) -> str:
    c = result["counts"]
    lines = [
        f"Tosca Analyzer requirement check for {issue_key}",
        f"Test case: {test_case}",
        f"Design match: {result['design_match']} / {result['expected_steps']} expected steps fully covered "
        f"(matched {c['matched']}, partial {c['partial']}, mismatch {c['mismatch']}, missing {c['missing']}, extra {c['extra']})",
    ]
    gaps = [r for r in result["rows"] if r["status"] != "matched"]
    if gaps:
        lines.append("")
        lines.append("Gaps:")
        for r in gaps:
            label = f"Step {r['n']}" if r["n"] else "Extra step"
            lines.append(f"- {label} ({r['status']}): {r['action']} — {r['hint']}")
    return "\n".join(lines)
