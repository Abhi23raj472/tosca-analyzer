"""Run a rule set against a workspace and produce the report payload."""
from __future__ import annotations

from dataclasses import asdict

from .model import Workspace
from .rules import CATEGORIES, CATEGORY_LABELS, RULES, Ctx, Finding
from . import docs, execution

SEVERITY_BASE = {"high": 26.0, "medium": 12.0, "low": 5.0}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def default_rule_set() -> dict:
    return {
        "id": "tricentis-default",
        "name": "Tricentis best practices",
        "builtin": True,
        "categories": [k for k, _, _ in CATEGORIES],
        "rules": {r.id: {"enabled": True, "severity": r.severity, "params": dict(r.params)} for r in RULES},
    }


def rule_catalog() -> list[dict]:
    return [r.meta() for r in RULES]


def _penalty(f: Finding, total_tcs: int) -> float:
    ids = f.affected_ids
    spread = 1.0 if not ids or not total_tcs else min(1.0, 0.35 + 1.3 * len(ids) / total_tcs)
    return SEVERITY_BASE.get(f.severity, 5.0) * spread


def score(findings: list[Finding], categories: list[str], total_tcs: int, exclude_high: bool = False) -> tuple[int, dict]:
    per_cat: dict[str, float] = {k: 0.0 for k in categories}
    for f in findings:
        if f.category in per_cat and not (exclude_high and f.severity == "high"):
            per_cat[f.category] += _penalty(f, total_tcs)
    cat_scores = {k: max(0, round(100 - p)) for k, p in per_cat.items()}
    weights = {k: w for k, _, w in CATEGORIES if k in cat_scores}
    total_w = sum(weights.values()) or 1
    overall = round(sum(cat_scores[k] * w for k, w in weights.items()) / total_w)
    return overall, cat_scores


def run_rules(ws: Workspace, rule_set: dict | None = None, docs_version: str = docs.DEFAULT_VERSION,
              categories: list[str] | None = None) -> tuple[list[Finding], list[str], int]:
    rs = rule_set or default_rule_set()
    cats = [c for c in (categories or rs.get("categories") or [k for k, _, _ in CATEGORIES]) if c in CATEGORY_LABELS]
    findings: list[Finding] = []
    ran = 0
    for r in RULES:
        cfg = rs.get("rules", {}).get(r.id, {})
        if not cfg.get("enabled", True) or r.category not in cats:
            continue
        ran += 1
        params = {**r.params, **(cfg.get("params") or {})}
        ctx = Ctx(ws, r, params, docs_version, cfg.get("severity") or r.severity)
        try:
            findings.extend(r.check(ctx))
        except Exception as exc:  # a broken rule must not sink the whole analysis
            ws.warnings.append(f"Rule {r.id} could not run: {exc}")
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 3), -len(f.occurrences), f.rule_id))
    return findings, cats, ran


def _step_payload(s) -> dict:
    return {"index": s.index, "name": s.name, "kind": s.kind, "module": s.module, "reference": s.reference,
            "disabled": s.disabled, "folder": " › ".join(s.folder_path),
            "values": [{"name": v.name, "value": v.value, "action_mode": v.action_mode} for v in s.values]}


def analyze(ws: Workspace, file_name: str, rule_set: dict | None = None, categories: list[str] | None = None,
            docs_version: str = docs.DEFAULT_VERSION, results: list[dict] | None = None) -> dict:
    rs = rule_set or default_rule_set()
    findings, cats, ran = run_rules(ws, rs, docs_version, categories)
    total_tcs = len(ws.test_cases)

    exec_summary = None
    if results:
        execution.match_results(results, ws.test_cases)
        exec_summary = execution.summarize(results, findings)

    overall, cat_scores = score(findings, cats, total_tcs)
    projected, _ = score(findings, cats, total_tcs, exclude_high=True)
    highs = [f for f in findings if f.severity == "high"]

    return {
        "file_name": file_name,
        "workspace": ws.name,
        "source_format": ws.source_format,
        "rule_set": {"id": rs.get("id"), "name": rs.get("name"), "rules_run": ran},
        "docs_version": docs_version,
        "docs_home": docs.link("overview", docs_version)["url"],
        "summary": {
            "score": overall,
            "projected_score": projected if highs else overall,
            "high_findings": len(highs),
            "test_cases": total_tcs,
            "steps": ws.step_count,
            "findings": len(findings),
            "occurrences": sum(len(f.occurrences) for f in findings),
            "by_severity": {s: sum(1 for f in findings if f.severity == s) for s in ("high", "medium", "low")},
        },
        "categories": [
            {"key": k, "label": CATEGORY_LABELS[k], "score": cat_scores[k],
             "findings": sum(1 for f in findings if f.category == k)}
            for k, _, _ in CATEGORIES if k in cat_scores
        ],
        "findings": [asdict(f) for f in findings],
        "execution": exec_summary,
        "results": results or [],
        "test_cases": [
            {"id": tc.id, "name": tc.name, "breadcrumb": tc.breadcrumb, "description": tc.description,
             "requirement_keys": tc.requirement_keys, "steps": [_step_payload(s) for s in tc.steps]}
            for tc in ws.test_cases
        ],
        "blocks": [{"name": b.name, "parameters": b.parameters, "steps": [_step_payload(s) for s in b.steps]}
                   for b in ws.blocks],
        "warnings": ws.warnings,
    }
