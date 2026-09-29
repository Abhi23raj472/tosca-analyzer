"""Execution results: parse run exports and link failures to findings."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from . import xlsx_reader
from .parser import ParseError, _attrs, _get, _local, unwrap

PASSED = {"passed", "pass", "ok", "success", "succeeded", "green"}
FAILED = {"failed", "fail", "failure", "error", "errored", "broken", "red"}
NOT_RUN = {"notrun", "not run", "noresult", "no result", "skipped", "skip", "notexecuted", "not executed", "blocked", "pending"}


def _status(raw: str) -> str:
    s = (raw or "").strip().lower().replace("_", " ")
    if s in PASSED:
        return "passed"
    if s in FAILED:
        return "failed"
    if s in NOT_RUN or s.replace(" ", "") in NOT_RUN or not s:
        return "not_run"
    return "failed" if "fail" in s or "error" in s else ("passed" if "pass" in s else "not_run")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def parse_results(data: bytes, filename: str, pdf_text: str | None = None) -> list[dict]:
    """Return [{name, status, message, duration}] from XML, Excel, or PDF text."""
    if pdf_text is not None:
        return _from_text(pdf_text)
    payload, container = unwrap(data)
    if container == "xlsx" or filename.lower().endswith(".xlsx"):
        return _from_xlsx(payload)
    try:
        root = ET.fromstring(payload.lstrip(b"\xef\xbb\xbf"))
    except ET.ParseError as exc:
        raise ParseError(f"The execution results file isn't valid XML ({exc}).") from exc
    results = _from_xml(root)
    if not results:
        raise ParseError("No test results were found. Upload a JUnit XML or a Tosca execution list export.")
    return results


def _from_xml(root: ET.Element) -> list[dict]:
    out: list[dict] = []
    # JUnit style
    if _local(root.tag) in {"testsuites", "testsuite"}:
        for tc in root.iter():
            if _local(tc.tag) != "testcase":
                continue
            status, msg = "passed", ""
            for child in tc:
                t = _local(child.tag)
                if t in {"failure", "error"}:
                    status, msg = "failed", child.get("message") or (child.text or "").strip()
                elif t == "skipped":
                    status, msg = "not_run", child.get("message") or ""
            out.append({"name": tc.get("name", ""), "status": status, "message": msg[:500],
                        "duration": tc.get("time", "")})
        return out
    # Tosca execution lists and generic exports: elements with a name and a result/status.
    # Keep only the innermost ones, so an ExecutionList that has its own Result doesn't count as a test.
    skip_tags = {"teststep", "xteststep", "teststepvalue", "step", "log", "steplog"}
    candidates = [el for el in root.iter()
                  if _local(el.tag) not in skip_tags
                  and _get(el, "Result", "Status", "ExecutionResult", "Verdict")
                  and _get(el, "TestCase", "TestCaseName", "Name")]
    ids = {id(el) for el in candidates}
    for el in candidates:
        if any(id(d) in ids for d in el.iter() if d is not el):
            continue
        attrs = _attrs(el)
        out.append({"name": _get(el, "TestCase", "TestCaseName", "Name"),
                    "status": _status(_get(el, "Result", "Status", "ExecutionResult", "Verdict")),
                    "message": (_get(el, "Message", "Error", "Details", "Log") or attrs.get("message", ""))[:500],
                    "duration": _get(el, "Duration", "Time")})
    return out


def _from_xlsx(data: bytes) -> list[dict]:
    out = []
    for rows in xlsx_reader.read_sheets(data).values():
        for row in xlsx_reader.table_dicts(rows):
            low = {k.strip().lower(): v for k, v in row.items()}
            name = next((low[k] for k in ("test case", "testcase", "name", "test case name", "test") if k in low), "")
            status = next((low[k] for k in ("result", "status", "verdict", "execution result") if k in low), "")
            if name and status:
                out.append({"name": str(name), "status": _status(str(status)),
                            "message": str(next((low[k] for k in ("message", "error", "details", "comment") if k in low), ""))[:500],
                            "duration": str(low.get("duration", ""))})
    if not out:
        raise ParseError("The sheet needs 'Test Case' and 'Result' (or 'Status') columns.")
    return out


_LINE = re.compile(r"^(?P<name>.+?)\s+(?P<status>passed|failed|error|not run|no result|skipped)\b(?P<rest>.*)$", re.I)


def _from_text(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = _LINE.match(line.strip())
        if m and len(m.group("name")) > 2:
            out.append({"name": m.group("name").strip(" .:-|"), "status": _status(m.group("status")),
                        "message": m.group("rest").strip(" -:|")[:500], "duration": ""})
    if not out:
        raise ParseError("No test results were recognised in the PDF. Each result line needs a test case name "
                         "followed by Passed, Failed or Not run.")
    return out


def match_results(results: list[dict], test_cases) -> dict[str, list[dict]]:
    """Map test case id -> results. Matches by name, then by a name contained in the result path."""
    by_name = {}
    for tc in test_cases:
        by_name.setdefault(_norm(tc.name), []).append(tc)
        by_name.setdefault(_norm(tc.breadcrumb), []).append(tc)
    out: dict[str, list[dict]] = {}
    for r in results:
        key = _norm(r["name"])
        tcs = by_name.get(key)
        if not tcs:
            tcs = [tc for tc in test_cases if len(_norm(tc.name)) > 3 and _norm(tc.name) in key][:1]
        for tc in tcs[:1]:
            out.setdefault(tc.id, []).append(r)
            r["test_case_id"] = tc.id
    return out


def summarize(results: list[dict], findings) -> dict:
    """Counts plus how many failures trace back to at least one finding."""
    counts = {"passed": 0, "failed": 0, "not_run": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    failed_ids = [r.get("test_case_id") for r in results if r["status"] == "failed"]
    traced = 0
    for f in findings:
        affected = f.affected_ids
        f.linked_failures = sorted({tid for tid in failed_ids if tid and tid in affected})
    for tid in failed_ids:
        if tid and any(tid in f.affected_ids for f in findings):
            traced += 1
    return {**counts, "total": len(results), "failures_traced": traced,
            "unmatched": sum(1 for r in results if not r.get("test_case_id"))}
