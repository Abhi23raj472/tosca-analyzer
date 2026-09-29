"""Precompute the sample report for the browser demo so its first screen needs no engine start-up.

    python backend/scripts/build_demo_data.py
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
from app.engine import analyze_file, parse_execution, requirement_check, rule_catalog, default_rule_set  # noqa: E402
from app.engine.rules import CATEGORIES  # noqa: E402
from app.engine.requirement import comment_text  # noqa: E402

OUT = BACKEND.parent / "frontend" / "src" / "demo"
OUT.mkdir(parents=True, exist_ok=True)
S = BACKEND / "samples"

run = parse_execution((S / "Claims_Run.xml").read_bytes(), "Claims_Run.xml")
report = analyze_file((S / "Claims_Regression.xml").read_bytes(), "Claims_Regression.tsu", results=run)
report["id"] = "sample-claims"
report["created_at"] = datetime(2026, 9, 27, 9, 30, tzinfo=timezone.utc).isoformat()
report["sample"] = True
issue = json.loads((S / "CLM-1482.json").read_text())
issue = {**issue, "source": "jira", "steps_source": "sample", "warnings": []}
tc = next(t for t in report["test_cases"] if "CLM-1482" in t["requirement_keys"])
check = requirement_check(issue["steps"], tc["steps"], issue["acceptance_criteria"])
check = {**check, "id": "sample-check", "test_case": tc["breadcrumb"],
         "comment": comment_text(issue["key"], tc["breadcrumb"], check)}

(OUT / "sample-report.json").write_text(json.dumps(report))
(OUT / "sample-issue.json").write_text(json.dumps(issue))
(OUT / "sample-check.json").write_text(json.dumps(check))
(OUT / "rules.json").write_text(json.dumps({
    "rules": rule_catalog(),
    "categories": [{"key": k, "label": l, "weight": w} for k, l, w in CATEGORIES],
    "default_rule_set": default_rule_set(),
}))
for name in ("Claims_Regression.xml", "Claims_Run.xml"):
    shutil.copy(S / name, OUT / name)
print("demo data written to", OUT)
