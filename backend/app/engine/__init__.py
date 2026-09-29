"""Tosca Analyzer engine (standard library only).

Public API used by both the FastAPI server and the in-browser demo:

    analyze_file(data, filename, rule_set=None, categories=None, docs_version=..., results=None) -> dict
    parse_execution(data, filename, pdf_text=None) -> list[dict]
    requirement_check(expected, steps, acceptance) -> dict
"""
from __future__ import annotations

from . import analyzer, docs, execution, parser, requirement, rules
from .parser import ParseError

__all__ = ["analyze_file", "parse_execution", "requirement_check", "rule_catalog", "default_rule_set", "ParseError"]


def analyze_file(data: bytes, filename: str, rule_set: dict | None = None, categories: list[str] | None = None,
                 docs_version: str = docs.DEFAULT_VERSION, results: list[dict] | None = None) -> dict:
    ws = parser.parse_bytes(data, filename)
    return analyzer.analyze(ws, filename, rule_set, categories, docs_version, results)


def parse_execution(data: bytes, filename: str, pdf_text: str | None = None) -> list[dict]:
    return execution.parse_results(data, filename, pdf_text)


def requirement_check(expected: list[dict], steps: list[dict], acceptance: list[str] | None = None) -> dict:
    return requirement.check(expected, steps, acceptance)


rule_catalog = analyzer.rule_catalog
default_rule_set = analyzer.default_rule_set
