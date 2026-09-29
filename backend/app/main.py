"""Tosca Analyzer API (FastAPI).

Run locally:  uvicorn app.main:app --reload
Interactive docs: http://localhost:8000/docs
"""
from __future__ import annotations

import io
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, db, docs_check, exports
from .engine import ParseError, analyze_file, parse_execution, requirement_check, rule_catalog
from .engine import analyzer, execution
from .engine.requirement import comment_text
from .integrations import jira, rally
from .integrations.jira import IntegrationError

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Tosca Analyzer", version="1.0.0", lifespan=lifespan,
              description="Checks Tricentis Tosca test cases against best practices and requirement tickets.")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _auth(request: Request, call_next):
    if config.API_TOKEN and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        if request.headers.get("authorization", "") != f"Bearer {config.API_TOKEN}":
            return JSONResponse({"detail": "Missing or invalid API token."}, status_code=401)
    return await call_next(request)


@app.exception_handler(ParseError)
def _parse_error(_: Request, exc: ParseError):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(IntegrationError)
def _integration_error(_: Request, exc: IntegrationError):
    return JSONResponse({"detail": str(exc)}, status_code=502)


async def _read_upload(f: UploadFile) -> bytes:
    data = await f.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"The file is larger than {config.MAX_UPLOAD_MB} MB.")
    if not data:
        raise HTTPException(422, "The uploaded file is empty.")
    return data


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _results(data: bytes, name: str) -> list[dict]:
    if name.lower().endswith(".pdf"):
        return parse_execution(b"", name, pdf_text=_pdf_text(data))
    return parse_execution(data, name)


# ---------------------------------------------------------------- health, rules, settings

@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/api/rules")
def rules():
    return {"rules": rule_catalog(), "categories": [{"key": k, "label": l, "weight": w} for k, l, w in analyzer.CATEGORIES]}


@app.get("/api/settings")
def get_settings(s: Session = Depends(db.get_db)):
    return db.public_settings(db.load_settings(s))


@app.put("/api/settings")
def put_settings(body: dict, s: Session = Depends(db.get_db)):
    return db.public_settings(db.save_settings(s, body))


@app.get("/api/docs/check")
def check_docs(version: Optional[str] = None, s: Session = Depends(db.get_db)):
    v = version or db.load_settings(s)["docs_version"]
    return {"version": v, "topics": docs_check.check(v)}


# ---------------------------------------------------------------- rule sets

class RuleSetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    categories: list[str]
    rules: dict[str, dict]


@app.get("/api/rule-sets")
def get_rule_sets(s: Session = Depends(db.get_db)):
    return db.list_rule_sets(s)


@app.post("/api/rule-sets", status_code=201)
def create_rule_set(body: RuleSetIn, s: Session = Depends(db.get_db)):
    rs = db.RuleSet(name=body.name, config=body.model_dump())
    s.add(rs)
    s.commit()
    return rs.to_dict()


@app.put("/api/rule-sets/{rs_id}")
def update_rule_set(rs_id: str, body: RuleSetIn, s: Session = Depends(db.get_db)):
    rs = s.get(db.RuleSet, rs_id)
    if not rs:
        raise HTTPException(404, "Rule set not found.")
    if rs_id == "tricentis-default":
        raise HTTPException(400, "The Tricentis default rule set can't be edited. Duplicate it first.")
    rs.name, rs.config = body.name, body.model_dump()
    s.commit()
    return rs.to_dict()


@app.delete("/api/rule-sets/{rs_id}", status_code=204)
def delete_rule_set(rs_id: str, s: Session = Depends(db.get_db)):
    if rs_id == "tricentis-default":
        raise HTTPException(400, "The Tricentis default rule set can't be deleted.")
    rs = s.get(db.RuleSet, rs_id)
    if rs:
        s.delete(rs)
        s.commit()


# ---------------------------------------------------------------- analyses

@app.post("/api/analyses", status_code=201)
async def create_analysis(
    file: UploadFile = File(..., description="Workspace subset (.tsu), XML export or Excel test case sheet"),
    results: Optional[UploadFile] = File(None, description="Optional execution results (XML, Excel or PDF)"),
    rule_set_id: str = Form("tricentis-default"),
    categories: str = Form("", description="Comma-separated category keys; empty means the rule set's own"),
    s: Session = Depends(db.get_db),
):
    data = await _read_upload(file)
    rs_row = s.get(db.RuleSet, rule_set_id) or s.get(db.RuleSet, "tricentis-default")
    rule_set = rs_row.to_dict()
    settings = db.load_settings(s)
    run_results = _results(await _read_upload(results), results.filename) if results and results.filename else None
    cats = [c for c in categories.split(",") if c] or None
    report = analyze_file(data, file.filename or "upload.xml", rule_set, cats, settings["docs_version"], run_results)
    if settings.get("docs_live_check"):
        docs_check.annotate(report, settings["docs_version"])
    row = db.Analysis(file_name=file.filename or "upload", score=report["summary"]["score"],
                      rule_set_name=rule_set["name"], report={**report, "categories_selected": cats})
    s.add(row)
    s.commit()
    return {"id": row.id, "created_at": row.created_at.isoformat(), **report}


@app.post("/api/analyses/{analysis_id}/results")
async def attach_results(analysis_id: str, results: UploadFile = File(...), s: Session = Depends(db.get_db)):
    """Link an execution run to an existing analysis (re-runs the rules on the stored source)."""
    row = s.get(db.Analysis, analysis_id)
    if not row:
        raise HTTPException(404, "Analysis not found.")
    run = _results(await _read_upload(results), results.filename or "results.xml")
    report = dict(row.report)
    # Re-link against the stored findings; the source file isn't kept, so rules aren't re-run.
    tcs = [SimpleNamespace(id=t["id"], name=t["name"], breadcrumb=t["breadcrumb"]) for t in report["test_cases"]]
    execution.match_results(run, tcs)
    failed = {r.get("test_case_id") for r in run if r["status"] == "failed"}
    traced = set()
    for f in report["findings"]:
        ids = {o.get("test_case_id") for o in f["occurrences"] if o.get("test_case_id")}
        f["linked_failures"] = sorted(ids & failed)
        traced |= ids & failed
    counts = {k: sum(1 for r in run if r["status"] == k) for k in ("passed", "failed", "not_run")}
    report["execution"] = {**counts, "total": len(run), "failures_traced": len(traced - {None}),
                           "unmatched": sum(1 for r in run if not r.get("test_case_id"))}
    report["results"] = run
    row.report = report
    s.commit()
    return {"id": row.id, "created_at": row.created_at.isoformat(), **report}


@app.get("/api/analyses")
def list_analyses(limit: int = 50, s: Session = Depends(db.get_db)):
    rows = s.scalars(select(db.Analysis).order_by(db.Analysis.created_at.desc()).limit(limit))
    return [r.summary() for r in rows]


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str, s: Session = Depends(db.get_db)):
    row = s.get(db.Analysis, analysis_id)
    if not row:
        raise HTTPException(404, "Analysis not found.")
    return {"id": row.id, "created_at": row.created_at.isoformat(), **row.report}


@app.delete("/api/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, s: Session = Depends(db.get_db)):
    row = s.get(db.Analysis, analysis_id)
    if row:
        s.delete(row)
        s.commit()


@app.get("/api/analyses/{analysis_id}/export.{fmt}")
def export_analysis(analysis_id: str, fmt: str, s: Session = Depends(db.get_db)):
    row = s.get(db.Analysis, analysis_id)
    if not row:
        raise HTTPException(404, "Analysis not found.")
    stamp = exports.stamp(row.created_at)
    base = row.file_name.rsplit(".", 1)[0]
    if fmt == "xlsx":
        return Response(exports.to_xlsx(row.report, stamp),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{base}_analysis.xlsx"'})
    if fmt == "pdf":
        return Response(exports.to_pdf(row.report, stamp), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{base}_analysis.pdf"'})
    raise HTTPException(404, "Export format must be xlsx or pdf.")


# ---------------------------------------------------------------- requirement check

class FetchIn(BaseModel):
    source: str = "jira"
    key: str


class CheckIn(BaseModel):
    analysis_id: str
    test_case_id: str
    issue: dict  # {key, steps: [{action, expected}], acceptance_criteria: [...]}


class PostIn(BaseModel):
    check_id: str


@app.post("/api/requirements/fetch")
def fetch_requirement(body: FetchIn, s: Session = Depends(db.get_db)):
    settings = db.load_settings(s)
    if body.source == "rally":
        return rally.fetch_item(settings["rally"], body.key)
    return jira.fetch_issue(settings["jira"], body.key)


@app.get("/api/analyses/{analysis_id}/match")
def match_test_case(analysis_id: str, key: str, s: Session = Depends(db.get_db)):
    """Find the test case that stores this issue key (the auto-match on the requirement screen)."""
    row = s.get(db.Analysis, analysis_id)
    if not row:
        raise HTTPException(404, "Analysis not found.")
    for t in row.report["test_cases"]:
        if key.upper() in [k.upper() for k in t.get("requirement_keys", [])]:
            return {"test_case_id": t["id"], "breadcrumb": t["breadcrumb"]}
    return {"test_case_id": None}


@app.post("/api/requirements/check")
def check_requirement(body: CheckIn, s: Session = Depends(db.get_db)):
    row = s.get(db.Analysis, body.analysis_id)
    if not row:
        raise HTTPException(404, "Analysis not found.")
    tc = next((t for t in row.report["test_cases"] if t["id"] == body.test_case_id), None)
    if not tc:
        raise HTTPException(404, "Test case not found in that analysis.")
    steps = body.issue.get("steps") or []
    if not steps:
        raise HTTPException(422, "The ticket has no manual test steps to compare.")
    result = requirement_check(steps, tc["steps"], body.issue.get("acceptance_criteria") or [])
    rc = db.RequirementCheck(issue_key=body.issue.get("key", ""), analysis_id=row.id, test_case_id=tc["id"],
                             result={**result, "issue": body.issue, "test_case": tc["breadcrumb"]})
    s.add(rc)
    s.commit()
    return {"id": rc.id, **result, "test_case": tc["breadcrumb"],
            "comment": comment_text(body.issue.get("key", ""), tc["breadcrumb"], result)}


@app.post("/api/requirements/post")
def post_requirement(body: PostIn, s: Session = Depends(db.get_db)):
    rc = s.get(db.RequirementCheck, body.check_id)
    if not rc:
        raise HTTPException(404, "Run the requirement check first.")
    settings = db.load_settings(s)
    issue = rc.result["issue"]
    text = comment_text(rc.issue_key, rc.result["test_case"], rc.result)
    if issue.get("source") == "rally":
        if not issue.get("ref"):
            raise HTTPException(422, "Fetch the Rally item again before posting.")
        posted = rally.post_discussion(settings["rally"], issue["ref"], text)
    else:
        posted = jira.post_comment(settings["jira"], rc.issue_key, text)
    rc.posted = posted
    s.commit()
    return {"posted": True, "id": posted, "issue": rc.issue_key}


# ---------------------------------------------------------------- frontend (production build)

if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = config.FRONTEND_DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(config.FRONTEND_DIST / "index.html")
