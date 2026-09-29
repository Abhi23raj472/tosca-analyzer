# Tosca Analyzer

Checks Tricentis Tosca test cases against Tricentis best practices, links execution failures to the problems that
caused them, and compares each Tosca test with the JIRA or Rally ticket it's supposed to implement.

| Screen | What it does |
|---|---|
| **New analysis** | Upload a workspace subset (`.tsu`), an XML export or an Excel test case sheet, plus an optional run (JUnit/Tosca XML, Excel or PDF). Pick a rule set and categories. |
| **Report** | Compliance score (0–100) with the score you'd reach after fixing high findings, category scores, execution summary, and every finding with its location, current vs suggested Tosca syntax and a link to the Tosca docs. Export Excel or PDF. |
| **Requirement check** | Pulls manual steps from JIRA (Xray Cloud, Xray Server/DC, Zephyr Scale or a numbered list in the description) or Rally, aligns them with the Tosca test case, and marks each step Matched / Partial / Mismatch / Missing / Extra. Posts the result back to the ticket. |
| **History, Rule sets, Settings** | Past reports; team copies of the rule set with per-rule severity and thresholds; JIRA, Rally and docs-version settings. |

## Architecture

```
backend/
  app/engine/          Analysis engine — standard library only, so it also runs in the browser (Pyodide)
    parser.py            .tsu / XML / zip / Excel -> Workspace model (tolerant of export variants)
    rules.py             The 20 rules (NAME, MOD, DATA, SYNC, VER, ERR, DOC)
    analyzer.py          Runs a rule set, scores categories, builds the report
    execution.py         Parses run results and links failures to findings
    requirement.py       Order-preserving alignment of ticket steps to Tosca steps
    docs.py              Tricentis documentation links per Tosca version
  app/integrations/    jira.py (Cloud + Server, Xray, Zephyr Scale), rally.py
  app/exports.py       Excel (openpyxl) and PDF (ReportLab)
  app/docs_check.py    Verifies documentation links at analysis time (cached 12 h)
  app/db.py            SQLAlchemy models: analyses, rule sets, settings, requirement checks
  app/main.py          FastAPI routes; also serves the built frontend
  samples/             Sample suite (48 test cases), nightly run, JIRA ticket
  tests/               21 pytest tests (engine, integrations with mocked HTTP, API)
frontend/              React 18 + TypeScript + Vite
  src/api/backend.ts     HTTP client; falls back to the in-browser engine when no API answers
  src/api/pyodide.ts     Runs backend/app/engine in the browser
  src/pages/             The six screens
```

## Run it

**Docker (API + UI + PostgreSQL)**

```bash
cp .env.example .env        # add JIRA / Rally credentials, or set them later in Settings
docker compose up --build   # http://localhost:8000   API docs: http://localhost:8000/docs
```

**Local development**

```bash
# API
cd backend
pip install -r requirements.txt
python samples/generate_samples.py      # optional: regenerate sample files
uvicorn app.main:app --reload           # http://localhost:8000

# UI (another terminal)
cd frontend
npm install
npm run dev                             # http://localhost:5173, proxies /api to :8000

# Tests
cd backend && python -m pytest -q
```

`npm run build:demo` produces a single self-contained page (`frontend/artifact/`) that runs the engine in the
browser with no server. JIRA/Rally posting and PDF run results need the server.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/analyses` | multipart: `file`, optional `results`, `rule_set_id`, `categories` |
| GET | `/api/analyses`, `/api/analyses/{id}` | history, full report |
| POST | `/api/analyses/{id}/results` | link a run to an existing analysis |
| GET | `/api/analyses/{id}/export.xlsx` / `.pdf` | exports |
| GET | `/api/analyses/{id}/match?key=CLM-1482` | test case that stores that issue key |
| POST | `/api/requirements/fetch` | `{source: "jira" \| "rally", key}` |
| POST | `/api/requirements/check` | `{analysis_id, test_case_id, issue}` |
| POST | `/api/requirements/post` | `{check_id}` posts the result as a comment |
| GET/POST/PUT/DELETE | `/api/rule-sets` | team rule sets |
| GET/PUT | `/api/settings` | secrets are write-only and come back masked |
| GET | `/api/rules`, `/api/docs/check` | rule catalog, documentation link check |

Set `API_TOKEN` to require `Authorization: Bearer <token>` on every `/api` call (useful for CI pipelines).

## Rules

| ID | Severity | Checks |
|---|---|---|
| NAME-01 | Low | Default or copied test case names (optional naming regex) |
| NAME-02 | Low | Default test step names |
| NAME-03 | Low | Duplicate test case names in one folder |
| MOD-01 | Medium | Test cases longer than N steps |
| MOD-02 | Low | No Precondition / Process / Verification / Postcondition folders |
| MOD-04 | High | Step sequences copied across test cases instead of a Reusable TestStepBlock (medium under 10 copies) |
| MOD-05 | Medium | Fixed input values inside reusable blocks |
| DATA-01 | High | Hard-coded environment URLs → `{CP[BaseUrl]}` |
| DATA-02 | High | Plain-text credentials → encrypted test configuration parameter |
| DATA-03 | Medium | Same literal test data in many test cases → `{XL[...]}` |
| DATA-04 | Low | Fixed dates → `{DATE[][][format]}` |
| SYNC-01 | Medium | No WaitOn/Verify after opening the application |
| SYNC-02 | High | TBox Wait / fixed waits instead of WaitOn |
| SYNC-03 | Medium | Verify immediately after a click without WaitOn |
| VER-01 | Medium | Test cases that never verify |
| VER-02 | Low | Verify with an empty expected value |
| ERR-01 | Low | Disabled steps left in test cases |
| ERR-03 | Medium | No recovery or clean-up scenario |
| DOC-01 | Low | Missing descriptions |
| DOC-02 | Low | No JIRA/Rally key stored on the test case |

Scoring: each finding costs points by severity (high 26, medium 12, low 5), scaled by how many test cases it
touches; category scores are combined with weights (modularization, data and sync weigh most).

## Before production

- **Validate the parser against real exports.** The parser recognises Tosca objects by element name or type
  attribute and reads fields from attributes or child elements. Binary `.tsu` files that aren't gzip/zip/XML get a
  clear error asking for an XML export. Try 3+ real exports and extend `KIND_ALIASES` in `parser.py` if needed.
- **Check the JIRA step source for your site.** Xray Cloud, Xray Server and Zephyr Scale endpoints are implemented
  from their public APIs and tested with mocked responses only.
- **Secrets** are stored in the database for the MVP. Move them to a secrets manager (AWS Secrets Manager / SSM)
  before hosting for customers, and add real user accounts (the `API_TOKEN` gate is single-tenant).
