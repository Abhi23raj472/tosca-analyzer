import gzip
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["DOCS_LIVE_CHECK"] = "false"

from app.engine import ParseError, analyze_file, parse_execution, requirement_check  # noqa: E402
from app.engine.rules import RULES  # noqa: E402
from app.integrations import jira  # noqa: E402

SAMPLES = ROOT / "samples"


@pytest.fixture(scope="module")
def sample():
    return (SAMPLES / "Claims_Regression.xml").read_bytes()


@pytest.fixture(scope="module")
def report(sample):
    run = parse_execution((SAMPLES / "Claims_Run.xml").read_bytes(), "Claims_Run.xml")
    return analyze_file(sample, "Claims_Regression.xml", results=run)


def by_rule(report, rule_id):
    return [f for f in report["findings"] if f["rule_id"] == rule_id]


# ---------------------------------------------------------------- engine

def test_twenty_rules_with_unique_ids():
    ids = [r.id for r in RULES]
    assert len(ids) == 20 and len(set(ids)) == 20


def test_parses_sample(report):
    s = report["summary"]
    assert s["test_cases"] == 48
    assert s["steps"] > 200
    assert 0 <= s["score"] <= 100
    assert s["projected_score"] >= s["score"]


def test_gzip_wrapped_tsu_is_unpacked(sample):
    r = analyze_file(gzip.compress(sample), "Claims.tsu")
    assert r["summary"]["test_cases"] == 48 and r["source_format"] == "tsu"


def test_binary_file_gives_readable_error():
    with pytest.raises(ParseError, match="export"):
        analyze_file(b"\x00\x01binary", "odd.tsu")


def test_hard_coded_url(report):
    [f] = by_rule(report, "DATA-01")
    assert f["severity"] == "high"
    assert "14 test cases" in f["title"]
    assert "{CP[BaseUrl]}/claims" in f["suggested"]


def test_duplicate_login_sequence(report):
    f = by_rule(report, "MOD-04")[0]
    assert "22 test cases" in f["title"]
    assert "RTB_Login" in f["suggested"]


def test_fixed_wait_points_at_submit_claim(report):
    [f] = by_rule(report, "SYNC-02")
    assert f["location"].startswith("Claims › Submit Claim › Step 7")
    assert "WaitOn" in f["suggested"]


def test_recovery_scenario_missing(report):
    [f] = by_rule(report, "ERR-03")
    assert "recovery" in f["title"].lower()


def test_encrypted_password_not_flagged(report):
    assert by_rule(report, "DATA-02") == []


def test_execution_links_failures(report):
    ex = report["execution"]
    assert (ex["passed"], ex["failed"], ex["not_run"]) == (39, 7, 2)
    assert ex["failures_traced"] >= 5
    assert any(f["linked_failures"] for f in report["findings"])


def test_rule_can_be_disabled(sample):
    from app.engine import default_rule_set
    rs = default_rule_set()
    rs["rules"]["SYNC-02"]["enabled"] = False
    r = analyze_file(sample, "x.xml", rs)
    assert not by_rule(r, "SYNC-02")


def test_category_filter(sample):
    r = analyze_file(sample, "x.xml", categories=["naming"])
    assert {f["category"] for f in r["findings"]} <= {"naming"}
    assert [c["key"] for c in r["categories"]] == ["naming"]


def test_excel_test_case_sheet():
    from openpyxl import Workbook
    import io
    wb = Workbook()
    ws = wb.active
    ws.append(["Test Case", "Folder", "Step", "Value Name", "Value", "ActionMode"])
    ws.append(["Login works", "Portal", "OpenUrl", "Url", "https://qa.example.com", "Input"])
    ws.append(["Login works", "Portal", "Login", "User", "bob", "Input"])
    ws.append(["Login works", "Portal", "Login", "Password", "hunter22", "Input"])
    buf = io.BytesIO()
    wb.save(buf)
    r = analyze_file(buf.getvalue(), "cases.xlsx")
    assert r["summary"]["test_cases"] == 1
    assert by_rule(r, "DATA-01") and by_rule(r, "DATA-02")


# ---------------------------------------------------------------- requirement check

def test_requirement_check_matches_ticket(report):
    issue = json.loads((SAMPLES / "CLM-1482.json").read_text())
    tc = next(t for t in report["test_cases"] if t["name"] == "Submit Claim")
    res = requirement_check(issue["steps"], tc["steps"], issue["acceptance_criteria"])
    status = {r["n"]: r["status"] for r in res["rows"] if r["n"]}
    assert status == {1: "matched", 2: "partial", 3: "matched", 4: "matched", 5: "missing", 6: "matched", 7: "mismatch"}
    assert res["design_match"] == 4
    assert any(r["status"] == "extra" and "Print Summary" in r["built"][0] for r in res["rows"])
    assert res["criteria_covered"] == 2
    mismatch = next(r for r in res["rows"] if r["status"] == "mismatch")
    assert "Pending review" in mismatch["hint"]


def test_steps_from_description():
    steps, ac = jira.steps_from_text(
        "Steps\n1. Open the portal -> Login page shows\n2. Sign in as admin\n\nAcceptance criteria\n- Admin sees reports\n")
    assert steps == [{"action": "Open the portal", "expected": "Login page shows"},
                     {"action": "Sign in as admin", "expected": ""}]
    assert ac == ["Admin sees reports"]


def test_adf_to_text():
    doc = {"type": "doc", "content": [{"type": "orderedList", "content": [
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Do A -> B"}]}]}]}]}
    assert jira.adf_text(doc).strip() == "1. Do A -> B"


def test_fetch_issue_from_xray_server(monkeypatch):
    def handler(req: httpx.Request):
        if req.url.path.endswith("/issue/CLM-9"):
            return httpx.Response(200, json={"fields": {"summary": "S", "status": {"name": "Open"},
                                                        "issuetype": {"name": "Test"}, "description": "", "issuelinks": []}})
        if req.url.path.endswith("/test/CLM-9/step"):
            return httpx.Response(200, json=[{"step": {"raw": "Click <b>Go</b>"}, "data": {"raw": ""}, "result": {"raw": "Done"}}])
        return httpx.Response(404)

    cfg = {"base_url": "https://jira.example", "deployment": "server", "api_token": "t", "test_steps_source": "auto"}
    monkeypatch.setattr(jira, "_client", lambda c: httpx.Client(base_url="https://jira.example",
                                                                  transport=httpx.MockTransport(handler)))
    issue = jira.fetch_issue(cfg, "clm-9")
    assert issue["steps"] == [{"action": "Click Go", "expected": "Done"}]
    assert issue["steps_source"] == "xray_server"


# ---------------------------------------------------------------- API

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_flow(client, sample):
    r = client.post("/api/analyses", files={
        "file": ("Claims_Regression.xml", sample, "text/xml"),
        "results": ("Claims_Run.xml", (SAMPLES / "Claims_Run.xml").read_bytes(), "text/xml"),
    }, data={"rule_set_id": "tricentis-default"})
    assert r.status_code == 201, r.text
    rep = r.json()
    aid = rep["id"]
    assert rep["execution"]["failed"] == 7

    assert client.get("/api/analyses").json()[0]["id"] == aid
    x = client.get(f"/api/analyses/{aid}/export.xlsx")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    p = client.get(f"/api/analyses/{aid}/export.pdf")
    assert p.status_code == 200 and p.content[:4] == b"%PDF"

    m = client.get(f"/api/analyses/{aid}/match", params={"key": "CLM-1482"}).json()
    assert m["breadcrumb"] == "Claims › Submit Claim"
    issue = json.loads((SAMPLES / "CLM-1482.json").read_text())
    chk = client.post("/api/requirements/check", json={"analysis_id": aid, "test_case_id": m["test_case_id"], "issue": issue})
    assert chk.status_code == 200, chk.text
    assert chk.json()["design_match"] == 4
    assert "CLM-1482" in chk.json()["comment"]


def test_api_rejects_bad_file(client):
    r = client.post("/api/analyses", files={"file": ("x.tsu", b"\x00\x00", "application/octet-stream")})
    assert r.status_code == 422
    assert "export" in r.json()["detail"]


def test_rule_set_crud(client):
    base = client.get("/api/rule-sets").json()[0]
    body = {"name": "Optum claims team", "categories": base["categories"], "rules": base["rules"]}
    body["rules"]["DOC-01"]["enabled"] = False
    created = client.post("/api/rule-sets", json=body).json()
    assert created["rules"]["DOC-01"]["enabled"] is False
    assert client.put("/api/rule-sets/tricentis-default", json=body).status_code == 400
    assert client.delete(f"/api/rule-sets/{created['id']}").status_code == 204


def test_settings_mask_secrets(client):
    client.put("/api/settings", json={"jira": {"base_url": "https://acme.atlassian.net", "api_token": "secret"}})
    s = client.get("/api/settings").json()
    assert s["jira"]["api_token"] == "••••••••"
    client.put("/api/settings", json={"jira": {"api_token": "••••••••"}})  # masked value keeps the stored one
    from app import db
    with db.SessionLocal() as sess:
        assert db.load_settings(sess)["jira"]["api_token"] == "secret"
