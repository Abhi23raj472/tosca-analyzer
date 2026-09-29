"""Rally integration: fetch a test case's steps (or a user story's first test case) and post a discussion."""
from __future__ import annotations

import re

import httpx

from .jira import IntegrationError, TIMEOUT, steps_from_text, strip_html


def _client(cfg: dict) -> httpx.Client:
    if not cfg.get("api_key"):
        raise IntegrationError("Rally isn't connected. Add a Rally API key in Settings.")
    base = (cfg.get("base_url") or "https://rally1.rallydev.com").rstrip("/") + "/slm/webservice/v2.0"
    return httpx.Client(base_url=base, headers={"ZSESSIONID": cfg["api_key"]}, timeout=TIMEOUT)


def _query(c: httpx.Client, kind: str, formatted_id: str, fetch: str) -> dict | None:
    r = c.get(f"/{kind}", params={"query": f'(FormattedID = "{formatted_id}")', "fetch": fetch, "pagesize": 1})
    if r.status_code == 401:
        raise IntegrationError("Rally rejected the API key.")
    if r.status_code >= 400:
        raise IntegrationError(f"Rally returned {r.status_code} for {formatted_id}.")
    results = r.json().get("QueryResult", {}).get("Results", [])
    return results[0] if results else None


def fetch_item(cfg: dict, formatted_id: str) -> dict:
    fid = formatted_id.strip().upper()
    if not re.match(r"^(TC|US|DE)\d+$", fid):
        raise IntegrationError(f"'{fid}' doesn't look like a Rally ID (for example TC1234 or US5678).")
    with _client(cfg) as c:
        story = None
        if fid.startswith(("US", "DE")):
            kind = "hierarchicalrequirement" if fid.startswith("US") else "defect"
            story = _query(c, kind, fid, "FormattedID,Name,Description,TestCases,ScheduleState,c_AcceptanceCriteria")
            if not story:
                raise IntegrationError(f"{fid} wasn't found in Rally.")
            tcs = c.get(story["TestCases"]["_ref"], params={"fetch": "FormattedID", "pagesize": 1}).json() \
                if story.get("TestCases", {}).get("Count") else {}
            first = (tcs.get("QueryResult", {}).get("Results") or [None])[0]
            tc = _query(c, "testcase", first["FormattedID"], "FormattedID,Name,Steps,ValidationExpectedResult") if first else None
        else:
            tc = _query(c, "testcase", fid, "FormattedID,Name,Steps,ValidationExpectedResult,WorkProduct,LastVerdict")
            if not tc:
                raise IntegrationError(f"{fid} wasn't found in Rally.")
        steps: list[dict] = []
        if tc and tc.get("Steps", {}).get("Count"):
            data = c.get(tc["Steps"]["_ref"], params={"fetch": "StepIndex,Input,ExpectedResult", "pagesize": 200}).json()
            rows = sorted(data.get("QueryResult", {}).get("Results", []), key=lambda s: s.get("StepIndex", 0))
            steps = [{"action": strip_html(s.get("Input", "")), "expected": strip_html(s.get("ExpectedResult", ""))} for s in rows]
    item = story or tc
    ac_text = strip_html((story or {}).get("c_AcceptanceCriteria") or "")
    _, ac = steps_from_text("Acceptance criteria\n" + ac_text) if ac_text else ([], [])
    if not steps and story:
        steps, ac2 = steps_from_text(strip_html(story.get("Description", "")))
        ac = ac or ac2
    return {
        "source": "rally", "key": fid, "summary": item.get("Name", ""),
        "status": item.get("ScheduleState") or item.get("LastVerdict") or "",
        "type": "User story" if fid.startswith("US") else ("Defect" if fid.startswith("DE") else "Test case"),
        "steps": steps, "acceptance_criteria": ac, "steps_source": "rally",
        "linked_test": tc.get("FormattedID") if story and tc else None,
        "ref": item.get("_ref"), "warnings": [],
    }


def post_discussion(cfg: dict, ref: str, text: str) -> str:
    html_text = "<br/>".join(text.split("\n"))
    with _client(cfg) as c:
        r = c.post("/conversationpost/create", json={"ConversationPost": {"Artifact": ref, "Text": html_text}})
    if r.status_code >= 400:
        raise IntegrationError(f"Rally returned {r.status_code} when posting the result.")
    return r.json().get("CreateResult", {}).get("Object", {}).get("_refObjectUUID", "")
