"""The 20 core rules, derived from Tricentis Tosca best-practice guidance.

Each rule looks at the whole workspace and returns zero or more findings.
Findings group every occurrence of the same problem, so "hard-coded URL in 14
test cases" is one finding with 14 occurrences rather than 14 findings.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from .model import TestCase, TestStep, Workspace
from . import docs

SEVERITIES = ("high", "medium", "low")

CATEGORIES: list[tuple[str, str, float]] = [
    ("naming", "Naming conventions", 1.0),
    ("modularization", "Modularization & reuse", 1.5),
    ("data", "Parameters & test data", 1.5),
    ("sync", "Synchronization & waits", 1.5),
    ("verification", "Verification & error handling", 1.25),
    ("documentation", "Documentation", 0.75),
]
CATEGORY_LABELS = {k: label for k, label, _ in CATEGORIES}


@dataclass
class Finding:
    rule_id: str
    category: str
    severity: str
    title: str
    message: str
    location: str
    current: str
    suggested: str
    docs: dict
    occurrences: list[dict] = field(default_factory=list)  # {test_case_id, test_case, location, detail}
    linked_failures: list[str] = field(default_factory=list)

    @property
    def affected_ids(self) -> set[str]:
        return {o["test_case_id"] for o in self.occurrences if o.get("test_case_id")}


@dataclass
class Rule:
    id: str
    category: str
    severity: str
    name: str
    description: str
    docs_topic: str
    check: Callable[["Ctx"], list[Finding]]
    params: dict = field(default_factory=dict)

    def meta(self) -> dict:
        return {
            "id": self.id, "category": self.category, "category_label": CATEGORY_LABELS[self.category],
            "severity": self.severity, "name": self.name, "description": self.description,
            "docs_topic": self.docs_topic, "params": dict(self.params),
        }


class Ctx:
    """What a rule sees: the workspace, its effective params, and helpers."""

    def __init__(self, ws: Workspace, rule: Rule, params: dict, docs_version: str, severity: str):
        self.ws, self.rule, self.params, self.docs_version, self.severity = ws, rule, params, docs_version, severity
        self.blocks = {b.name.lower(): b for b in ws.blocks}

    def finding(self, title: str, message: str, occurrences: list[dict], current: str, suggested: str,
                location: Optional[str] = None) -> Finding:
        loc = location or (occurrences[0]["location"] if occurrences else "Workspace")
        return Finding(
            rule_id=self.rule.id, category=self.rule.category, severity=self.severity, title=title,
            message=message, location=loc, current=current, suggested=suggested,
            docs=docs.link(self.rule.docs_topic, self.docs_version), occurrences=occurrences,
        )

    def expanded_steps(self, tc: TestCase) -> list[TestStep]:
        """Steps with reusable-block references resolved (one level is enough for verification checks)."""
        out: list[TestStep] = []
        for s in tc.steps:
            if s.kind == "reference" and s.reference and s.reference.lower() in self.blocks:
                out.extend(self.blocks[s.reference.lower()].steps)
            else:
                out.append(s)
        return out


RULES: list[Rule] = []


def rule(id: str, category: str, severity: str, name: str, description: str, docs_topic: str, **params):
    def deco(fn):
        RULES.append(Rule(id, category, severity, name, description, docs_topic, fn, params))
        return fn
    return deco


# ---------------------------------------------------------------- shared helpers

PARAM_REF = re.compile(r"\{(CP|B|PL|XL|TDS|TCP|ENCRYPTED|MATH|DATE|RND|CALC|STRINGTOLOWER|STRINGTOUPPER)\b.*?\}", re.I)
CLICKS = {"{click}", "click", "x", "{leftclick}", "{doubleclick}", "{rightclick}", "{altclick}", "{sendkeys[enter]}"}
URL = re.compile(r"https?://[^\s\"'<>{}]+", re.I)
CRED_NAME = re.compile(r"pass(word)?|pwd|secret|token|api.?key|credential", re.I)
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b")
WAIT_NAME = re.compile(r"\b(wait|sleep|delay|pause)\b", re.I)
WAIT_VALUE_NAME = re.compile(r"^(duration|wait ?time|time|milliseconds|seconds|delay|waitbefore|waitafter|sleep)$", re.I)
OPEN_URL = re.compile(r"open ?url|navigate|open ?browser|start ?browser|open ?application", re.I)


def is_param(value: str) -> bool:
    return bool(PARAM_REF.search(value or ""))


def is_click(value: str) -> bool:
    return (value or "").strip().lower() in CLICKS


def is_literal_input(v) -> bool:
    val = (v.value or "").strip()
    return (v.action_mode.lower() == "input" and bool(val) and not is_param(val) and not is_click(val)
            and not v.disabled)


def step_loc(tc: TestCase, step: TestStep) -> str:
    return f"{tc.breadcrumb} › Step {step.index} · {step.name}"


def occ(tc: TestCase, step: Optional[TestStep] = None, detail: str = "") -> dict:
    return {
        "test_case_id": tc.id, "test_case": tc.breadcrumb,
        "location": step_loc(tc, step) if step else tc.breadcrumb,
        "detail": detail,
    }


def ident(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "_".join(w[:1].upper() + w[1:] for w in words) or "Value"


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def says(n: int, word: str, one: str, many: str) -> str:
    """'1 test case has' / '3 test cases have'."""
    return f"{plural(n, word)} {one if n == 1 else many}"


def common_scope(tcs: list[TestCase]) -> str:
    tops = {tc.top_folder for tc in tcs}
    return f"{tops.pop()} › *" if len(tops) == 1 else "Multiple folders"


def active(tc: TestCase) -> list[TestStep]:
    return [s for s in tc.steps if not s.disabled]


# ---------------------------------------------------------------- Naming

DEFAULT_TC_NAME = re.compile(r"^(new ?test ?case\b.*|test ?case ?\d*|tc ?\d+|copy of .*|.*\(\d+\)|.*[ _-]copy\d*)$", re.I)
DEFAULT_STEP_NAME = re.compile(r"^(new ?test ?step\b.*|test ?step ?\d*|step ?\d+|unnamed step)$", re.I)


@rule("NAME-01", "naming", "low", "Default or copied test case names",
      "Test cases keep names like 'New TestCase' or 'Copy of …', so reports and execution lists don't say what failed.",
      "content", pattern="")
def name_default_testcase(c: Ctx):
    pat = re.compile(c.params["pattern"]) if c.params.get("pattern") else None
    hits = []
    for tc in c.ws.test_cases:
        if DEFAULT_TC_NAME.match(tc.name.strip()):
            hits.append(occ(tc, detail=f"'{tc.name}'"))
        elif pat and not pat.search(tc.name):
            hits.append(occ(tc, detail=f"'{tc.name}' doesn't match {c.params['pattern']}"))
    if not hits:
        return []
    first = hits[0]["detail"].split("'")[1] if "'" in hits[0]["detail"] else hits[0]["test_case"]
    return [c.finding(
        f"{plural(len(hits), 'test case')} with default or off-pattern names",
        "Name each test case after the business scenario it covers so a failed run is readable without opening Tosca.",
        hits, f"TestCase\n  Name = {first}", "TestCase\n  Name = <Business process> – <Scenario>",
    )]


@rule("NAME-02", "naming", "low", "Default test step names",
      "Steps named 'New TestStep' or 'Step 3' make logs and failure messages hard to trace.", "content")
def name_default_step(c: Ctx):
    hits = []
    for tc in c.ws.test_cases:
        for s in tc.steps:
            if DEFAULT_STEP_NAME.match(s.name.strip()):
                hits.append(occ(tc, s, s.name))
    if not hits:
        return []
    return [c.finding(
        says(len(hits), 'test step', 'keeps a default name', 'keep default names'),
        "Rename steps after the screen or action they drive, for example 'Enter claim amount'.",
        hits, f"TestStep\n  Name = {hits[0]['detail']}", "TestStep\n  Name = <Action> <Screen or control>",
    )]


@rule("NAME-03", "naming", "low", "Duplicate test case names in one folder",
      "Two test cases with the same name in the same folder can't be told apart in execution lists.", "content")
def name_duplicates(c: Ctx):
    groups: dict[tuple, list[TestCase]] = defaultdict(list)
    for tc in c.ws.test_cases:
        groups[(tuple(tc.path), tc.name.strip().lower())].append(tc)
    hits = []
    for tcs in groups.values():
        if len(tcs) > 1:
            for tc in tcs:
                hits.append(occ(tc, detail=f"{len(tcs)} test cases named '{tc.name}'"))
    if not hits:
        return []
    return [c.finding(
        says(len(hits), 'test case', 'shares a name with a sibling', 'share a name with a sibling'),
        "Give each test case a unique name within its folder, usually by adding the scenario variant.",
        hits, f"{hits[0]['test_case']}\n{hits[1]['test_case'] if len(hits) > 1 else ''}",
        f"{hits[0]['test_case']} – Happy path\n{hits[0]['test_case']} – Invalid input",
    )]


# ---------------------------------------------------------------- Modularization & reuse

@rule("MOD-01", "modularization", "medium", "Oversized test cases",
      "Very long test cases fail late, are slow to debug and usually mix several scenarios.", "content", max_steps=30)
def mod_oversized(c: Ctx):
    limit = int(c.params.get("max_steps", 30))
    hits = [occ(tc, detail=f"{len(tc.steps)} steps") for tc in c.ws.test_cases if len(tc.steps) > limit]
    if not hits:
        return []
    worst = max(c.ws.test_cases, key=lambda t: len(t.steps))
    return [c.finding(
        f"{plural(len(hits), 'test case')} longer than {limit} steps",
        "Split long test cases by scenario, and move shared setup into Reusable TestStepBlocks.",
        hits, f"{worst.name}\n  {len(worst.steps)} steps in one test case",
        f"{worst.name} – Part 1 (setup + scenario A)\n{worst.name} – Part 2 (scenario B)",
    )]


@rule("MOD-02", "modularization", "low", "No folder structure inside test cases",
      "Tricentis recommends grouping steps into folders such as Precondition, Process, Verification and Postcondition.",
      "content", min_steps=8)
def mod_structure(c: Ctx):
    limit = int(c.params.get("min_steps", 8))
    hits = [occ(tc, detail=f"{len(tc.steps)} steps, no folders")
            for tc in c.ws.test_cases if len(tc.steps) >= limit and not any(s.folder_path for s in tc.steps)]
    if not hits:
        return []
    return [c.finding(
        says(len(hits), 'test case', 'has no step folders', 'have no step folders'),
        "Group steps into TestStepFolders so the intent of each block is visible and Postcondition steps always run last.",
        hits, "TestCase\n  Step 1 … Step N (flat list)",
        "TestCase\n  Precondition › Process › Verification › Postcondition",
    )]


@rule("MOD-04", "modularization", "high", "Duplicated step sequences",
      "The same steps are copied into many test cases instead of living in one Reusable TestStepBlock.",
      "rtb", min_length=3, min_test_cases=3, high_at=10)
def mod_duplicates(c: Ctx):
    min_len = int(c.params.get("min_length", 3))
    min_tcs = int(c.params.get("min_test_cases", 3))
    seqs: dict[int, list[TestStep]] = {}
    sigs: dict[int, list[tuple]] = {}
    for i, tc in enumerate(c.ws.test_cases):
        steps = [s for s in active(tc) if s.kind == "step"]
        seqs[i], sigs[i] = steps, [s.signature() for s in steps]

    windows: dict[tuple, dict[int, int]] = defaultdict(dict)  # window -> {tc index: start pos}
    for i, sig in sigs.items():
        for p in range(len(sig) - min_len + 1):
            w = tuple(sig[p:p + min_len])
            windows[w].setdefault(i, p)

    found: list[tuple[list[int], dict[int, int], int]] = []
    used: set[tuple[int, int]] = set()
    for w, where in sorted(windows.items(), key=lambda kv: -len(kv[1])):
        if len(where) < min_tcs or any((i, k) in used for i, p in where.items() for k in range(p, p + min_len)):
            continue
        length = min_len
        while True:  # extend while every copy continues identically
            nxt = {sigs[i][p + length] if p + length < len(sigs[i]) else None for i, p in where.items()}
            if len(nxt) == 1 and None not in nxt:
                length += 1
            else:
                break
        for i, p in where.items():
            for k in range(p, p + length):
                used.add((i, k))
        found.append((sorted(where), where, length))
        if len(found) >= 3:
            break

    out = []
    for tc_idx, where, length in found:
        i0 = tc_idx[0]
        sample = seqs[i0][where[i0]:where[i0] + length]
        label = next((s.name for s in sample if re.search(r"log ?in|sign ?in|auth", s.text(), re.I)),
                     next((s.name for s in sample if not OPEN_URL.search(s.name)), sample[0].name))
        is_login = bool(re.search(r"log ?in|sign ?in|auth", " ".join(x.text() for x in sample), re.I))
        rtb = "RTB_Login" if is_login else "RTB_" + ident(re.sub(r"^(enter|open|click|go to)\s+", "", label, flags=re.I))
        params = []
        for s in sample:
            for v in s.values:
                if is_literal_input(v) and len(params) < 4:
                    params.append("{" + ident(v.name.split(".")[-1]) + "}")
        tcs = [c.ws.test_cases[i] for i in tc_idx]
        start = sample[0].index
        hits = [occ(tc, seqs[i][where[i]], f"steps {seqs[i][where[i]].index}–{seqs[i][where[i] + length - 1].index}")
                for i, tc in zip(tc_idx, tcs)]
        names = ", ".join(s.name for s in sample[:4]) + (" …" if length > 4 else "")
        out.append(c.finding(
            f"{'Login steps' if 'login' in rtb.lower() else 'Step sequence'} duplicated across {plural(len(tcs), 'test case')}",
            f"The same {length} steps ({names}) are copied into each test case. Move them to a Reusable "
            f"TestStepBlock in the Library so one change updates every test.",
            hits, f"{length} copied steps × {len(tcs)} test cases",
            f"Library › {rtb}" + (f"\n  Params: {', '.join(dict.fromkeys(params))}" if params else ""),
            location=f"{common_scope(tcs)} › Steps {start}–{start + length - 1}",
        ))
        if c.severity == "high" and len(tcs) < int(c.params.get("high_at", 10)):
            out[-1].severity = "medium"  # a handful of copies is a smell, not an emergency
    return out


@rule("MOD-05", "modularization", "medium", "Hard-coded values inside reusable blocks",
      "Reusable TestStepBlocks with fixed input values can only be reused for one data set.", "rtb")
def mod_block_literals(c: Ctx):
    out, sample = [], None
    for b in c.ws.blocks:
        lits = [(s, v) for s in b.steps for v in s.values if is_literal_input(v)]
        if lits:
            s, v = lits[0]
            sample = sample or (b, s, v)
            out.append({"test_case_id": "", "test_case": f"Library › {b.name}",
                        "location": f"Library › {b.name} › Step {s.index} · {s.name}",
                        "detail": f"{len(lits)} fixed input value(s)"})
    if not out:
        return []
    b, s, v = sample
    short = v.name.split(".")[-1]
    return [c.finding(
        says(len(out), 'reusable block', 'uses fixed input values', 'use fixed input values'),
        "Replace fixed values in the block with business parameters so each test case can pass its own data.",
        out, f"Library › {b.name} › {s.name}\n  {short} = {v.value}",
        f"Library › {b.name} › {s.name}\n  {short} = {{PL[{ident(short)}]}}",
    )]


# ---------------------------------------------------------------- Parameters & test data

@rule("DATA-01", "data", "high", "Hard-coded environment URLs",
      "URLs typed into steps break when the suite moves between environments.", "tcp")
def data_urls(c: Ctx):
    hits, sample = [], None
    for tc in c.ws.test_cases:
        for s in tc.steps:
            for v in s.values:
                m = URL.search(v.value or "")
                if m and not is_param(v.value):
                    hits.append(occ(tc, s, m.group(0)))
                    sample = sample or (s, v, m.group(0))
                    break
    if not hits:
        return []
    s, v, url = sample
    host = re.match(r"https?://[^/]+", url).group(0)
    rest = url[len(host):]
    cp = next((k for k, val in c.ws.config_params.items() if val and val.rstrip("/") == host), "BaseUrl")
    tcs = {h["test_case_id"] for h in hits}
    return [c.finding(
        f"Environment URL hard-coded in {plural(len(tcs), 'test case')}",
        "Hard-coded values break when the suite moves between environments. Store them once as a test "
        "configuration parameter and reference it.",
        hits, f"{s.name}\n  {v.name.split('.')[-1]} = {url}", f"{s.name}\n  {v.name.split('.')[-1]} = {{CP[{cp}]}}{rest}",
        location=f"{common_scope([t for t in c.ws.test_cases if t.id in tcs])} › Step {s.index} · {s.name}",
    )]


@rule("DATA-02", "data", "high", "Credentials in plain text",
      "Passwords and tokens typed as plain values are visible to everyone with workspace access.", "tcp")
def data_credentials(c: Ctx):
    hits, sample = [], None
    for tc in c.ws.test_cases:
        for s in tc.steps:
            for v in s.values:
                if (CRED_NAME.search(v.name) and is_literal_input(v) and v.data_type.lower() != "password"
                        and not v.value.startswith("*")):
                    hits.append(occ(tc, s, v.name))
                    sample = sample or (s, v)
    if not hits:
        return []
    s, v = sample
    return [c.finding(
        f"Plain-text credentials in {plural(len({h['test_case_id'] for h in hits}), 'test case')}",
        "Keep secrets out of test steps. Store the value once as an encrypted test configuration parameter "
        "(DataType Password) and reference it.",
        hits, f"{s.name}\n  {v.name} = {'•' * min(len(v.value), 8)}   (DataType: {v.data_type})",
        f"{s.name}\n  {v.name} = {{CP[{ident(v.name)}]}}   (DataType: Password)",
    )]


@rule("DATA-03", "data", "medium", "Repeated literal test data",
      "The same data value is typed into many test cases instead of coming from TestCase-Design or a test sheet.",
      "tcp", min_test_cases=5)
def data_repeated(c: Ctx):
    limit = int(c.params.get("min_test_cases", 5))
    seen: dict[tuple, dict[str, tuple]] = defaultdict(dict)
    for tc in c.ws.test_cases:
        for s in tc.steps:
            for v in s.values:
                val = (v.value or "").strip()
                if (not is_literal_input(v) or len(val) < 3 or URL.search(val) or CRED_NAME.search(v.name)
                        or val.lower() in {"true", "false", "yes", "no"} or re.fullmatch(r"\d{1,2}", val)):
                    continue
                seen[(v.name.split(".")[-1], val)].setdefault(tc.id, (tc, s))
    hits, top = [], None
    for (vname, val), where in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        if len(where) >= limit:
            top = top or (vname, val, len(where))
            for tc, s in where.values():
                hits.append(occ(tc, s, f"{vname} = {val}"))
    if not hits:
        return []
    vname, val, n = top
    return [c.finding(
        f"Same test data typed into {plural(n, 'test case')}",
        "Drive repeated values from TestCase-Design attributes or a test data sheet, so data changes happen in one place.",
        hits, f"{vname} = {val}\n  (copied into {n} test cases)", f"{vname} = {{XL[{ident(vname)}]}}",
    )]


@rule("DATA-04", "data", "low", "Hard-coded dates",
      "Fixed dates expire; tests that pass today fail when the date moves into the past or future.", "dates")
def data_dates(c: Ctx):
    hits, sample = [], None
    for tc in c.ws.test_cases:
        for s in tc.steps:
            for v in s.values:
                m = DATE.search(v.value or "")
                if m and not is_param(v.value) and not URL.search(v.value or "") and not v.disabled:
                    hits.append(occ(tc, s, f"{v.name} = {m.group(0)}"))
                    sample = sample or (s, v, m.group(0))
    if not hits:
        return []
    s, v, d = sample
    fmt = "yyyy-MM-dd" if re.match(r"\d{4}-", d) else ("dd.MM.yyyy" if "." in d else "MM/dd/yyyy")
    return [c.finding(
        f"Fixed dates in {plural(len({h['test_case_id'] for h in hits}), 'test case')}",
        "Use a dynamic date expression relative to today so the test keeps working as time passes.",
        hits, f"{s.name}\n  {v.name} = {d}", f"{s.name}\n  {v.name} = {{DATE[][][{fmt}]}}",
    )]


# ---------------------------------------------------------------- Synchronization & waits

def _is_wait_step(s: TestStep) -> Optional[str]:
    if WAIT_NAME.search(s.name) or WAIT_NAME.search(s.module):
        for v in s.values:
            if re.fullmatch(r"\d+(\.\d+)?", (v.value or "").strip()):
                return f"{v.value} ms" if float(v.value) > 100 else f"{v.value} s"
        return "fixed wait"
    for v in s.values:
        if WAIT_VALUE_NAME.match(v.name.split(".")[-1]) and re.fullmatch(r"\d+", (v.value or "").strip()):
            return f"{v.name} = {v.value}"
    return None


@rule("SYNC-01", "sync", "medium", "Page opened without synchronization",
      "After opening a URL or application, the next step acts before the page is confirmed ready.", "action_modes")
def sync_after_open(c: Ctx):
    hits = []
    for tc in c.ws.test_cases:
        steps = active(tc)
        for a, b in zip(steps, steps[1:]):
            if OPEN_URL.search(a.name) or OPEN_URL.search(a.module):
                if not any(v.action_mode.lower() in {"waiton", "verify"} for v in b.values) and b.kind == "step":
                    hits.append(occ(tc, b, f"after {a.name}"))
    if not hits:
        return []
    h = hits[0]
    step_name = h["location"].split("· ")[-1]
    return [c.finding(
        f"No wait after opening the application in {plural(len({x['test_case_id'] for x in hits}), 'test case')}",
        "Confirm the first screen is ready with a WaitOn before interacting with it.",
        hits, f"{step_name}\n  <first control> = …   (ActionMode: Input)",
        f"{step_name}\n  <page heading>.Visible = True   (ActionMode: WaitOn)",
    )]


@rule("SYNC-02", "sync", "high", "Fixed waits instead of synchronization",
      "Hard-coded waits slow every run and still fail when the app is slower than expected.", "wait_times")
def sync_fixed_waits(c: Ctx):
    hits, sample = [], None
    for tc in c.ws.test_cases:
        steps = active(tc)
        for i, s in enumerate(steps):
            d = _is_wait_step(s)
            if d:
                hits.append(occ(tc, s, d))
                if sample is None:
                    nxt = steps[i + 1] if i + 1 < len(steps) else None
                    sample = (s, d, nxt)
    if not hits:
        return []
    s, d, nxt = sample
    dur = next((v for v in s.values if re.fullmatch(r"\d+(\.\d+)?", (v.value or "").strip())), None)
    current = f"{s.name}\n  {dur.name} = {dur.value}   (ActionMode: {dur.action_mode})" if dur else f"{s.name}\n  ({d})"
    target = nxt.name if nxt else "<next control>"
    return [c.finding(
        "Fixed waits used instead of synchronization",
        "Hard-coded waits slow every run and still fail when the app is slower than expected. Let Tosca wait for "
        "the control state instead, using WaitOn with a timeout.",
        hits, current, f"{target}\n  Visible = True   (ActionMode: WaitOn)",
    )]


@rule("SYNC-03", "sync", "medium", "Verify right after a click",
      "A Verify that runs immediately after a click can read the old screen before the app has responded.",
      "action_modes")
def sync_click_verify(c: Ctx):
    hits = []
    for tc in c.ws.test_cases:
        steps = active(tc)
        for a, b in zip(steps, steps[1:]):
            clicked = any(is_click(v.value) and v.action_mode.lower() == "input" for v in a.values)
            modes = {v.action_mode.lower() for v in b.values}
            if clicked and b.values and modes == {"verify"} and (a.module or a.name) != (b.module or b.name):
                hits.append(occ(tc, b, f"verifies after clicking in '{a.name}'"))
    if not hits:
        return []
    step_name = hits[0]["location"].split("· ")[-1]
    return [c.finding(
        f"Verification races a click in {plural(len({x['test_case_id'] for x in hits}), 'test case')}",
        "Add a WaitOn for the element the click should produce, then verify.",
        hits, f"{step_name}\n  Status = …   (ActionMode: Verify)",
        f"{step_name}\n  Status.Visible = True   (ActionMode: WaitOn)\n  Status = …   (ActionMode: Verify)",
    )]


# ---------------------------------------------------------------- Verification & error handling

@rule("VER-01", "verification", "medium", "Test cases that never verify",
      "A test case without a Verify step passes as long as nothing crashes.", "action_modes")
def ver_none(c: Ctx):
    hits = []
    for tc in c.ws.test_cases:
        steps = [s for s in c.expanded_steps(tc) if not s.disabled]
        if steps and not any(v.action_mode.lower() == "verify" for s in steps for v in s.values):
            hits.append(occ(tc, detail=f"{len(steps)} steps, 0 verifications"))
    if not hits:
        return []
    return [c.finding(
        says(len(hits), 'test case', 'never verifies a result', 'never verify a result'),
        "End each scenario with at least one Verify on the business outcome, such as a status or confirmation text.",
        hits, f"{hits[0]['test_case'].split(' › ')[-1]}\n  (Input and click steps only)",
        "Confirmation Text\n  Text Contains \"…\"   (ActionMode: Verify)",
    )]


@rule("VER-02", "verification", "low", "Verify with an empty expected value",
      "An empty Verify value checks for an empty field, which is rarely what was intended.", "action_modes")
def ver_empty(c: Ctx):
    hits = []
    for tc in c.ws.test_cases:
        for s in tc.steps:
            for v in s.values:
                if v.action_mode.lower() == "verify" and not (v.value or "").strip() and not v.disabled:
                    hits.append(occ(tc, s, v.name))
    if not hits:
        return []
    return [c.finding(
        f"{plural(len(hits), 'verification')} with no expected value",
        "Fill in the expected value, or switch the ActionMode if the step should only wait for the control.",
        hits, f"{hits[0]['detail']} = (empty)   (ActionMode: Verify)",
        f"{hits[0]['detail']} = <expected value>   (ActionMode: Verify)",
    )]


@rule("ERR-01", "verification", "low", "Disabled steps left in test cases",
      "Disabled steps hide real coverage gaps and confuse whoever maintains the test next.", "error_handling")
def err_disabled(c: Ctx):
    hits = []
    for tc in c.ws.test_cases:
        for s in tc.steps:
            if s.disabled:
                hits.append(occ(tc, s, "disabled"))
    if not hits:
        return []
    return [c.finding(
        f"{plural(len(hits), 'disabled step')} left in test cases",
        "Delete steps that are no longer needed, or re-enable them and fix the underlying problem.",
        hits, f"{hits[0]['location'].split('· ')[-1]}   (Disabled)", "— removed, or re-enabled and fixed —",
    )]


@rule("ERR-03", "verification", "medium", "No recovery or clean-up scenario",
      "Without a recovery scenario, one unexpected dialog fails every following test in the run.", "recovery")
def err_recovery(c: Ctx):
    missing = []
    if not c.ws.recovery_scenarios:
        missing.append("recovery")
    if not c.ws.cleanup_scenarios:
        missing.append("clean-up")
    if not missing:
        return []
    scope = c.ws.test_cases[0].top_folder if c.ws.test_cases else c.ws.name
    both = len(missing) == 2
    return [c.finding(
        "No recovery or clean-up scenario defined" if both else f"No {missing[0]} scenario defined",
        "Without a recovery scenario, one unexpected dialog fails every following test in the run. A clean-up "
        "scenario returns the app to a known state before the next test.",
        [{"test_case_id": "", "test_case": scope, "location": f"{scope} (test case folder)",
          "detail": f"missing {' and '.join(missing)} scenario"}],
        "— none —",
        ("Recovery Scenario: Close unexpected popups\nCleanUp Scenario: Close browser and log out" if both else
         "Recovery Scenario: Close unexpected popups" if missing == ["recovery"] else
         "CleanUp Scenario: Close browser and log out"),
        location=f"{scope} (test case folder)",
    )]


# ---------------------------------------------------------------- Documentation

@rule("DOC-01", "documentation", "low", "Missing test case descriptions",
      "Without a description, reviewers can't tell what a test is meant to prove.", "content")
def doc_description(c: Ctx):
    hits = [occ(tc, detail="no description") for tc in c.ws.test_cases if len((tc.description or "").strip()) < 10]
    if not hits:
        return []
    return [c.finding(
        f"{plural(len(hits), 'test case')} without a description",
        "Add one or two sentences stating the scenario and its expected outcome.",
        hits, "Description = (empty)", "Description = Member submits a claim with a document; status becomes Pending review.",
    )]


@rule("DOC-02", "documentation", "low", "Test cases not linked to a requirement",
      "Unlinked test cases can't be traced to a JIRA or Rally item for coverage and audits.", "content")
def doc_requirement(c: Ctx):
    hits = [occ(tc, detail="no issue key") for tc in c.ws.test_cases if not tc.requirement_keys]
    if not hits:
        return []
    return [c.finding(
        f"{plural(len(hits), 'test case')} not linked to a requirement",
        "Store the JIRA or Rally key as a test case property so the requirement check and audits can find it.",
        hits, "Properties\n  (no JiraKey)", "Properties\n  JiraKey = CLM-1482",
    )]
