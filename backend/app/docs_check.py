"""Check that the Tricentis documentation pages the rules cite are reachable for a Tosca version."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from .engine import docs

_CACHE: dict[str, tuple[float, dict]] = {}
TTL = 12 * 3600


def _probe(url: str) -> dict:
    try:
        r = httpx.get(url, timeout=8.0, follow_redirects=True, headers={"User-Agent": "ToscaAnalyzer/1.0"})
        return {"ok": r.status_code < 400, "status": r.status_code}
    except httpx.HTTPError as exc:
        return {"ok": False, "status": None, "error": type(exc).__name__}


def check(version: str) -> dict:
    """{topic: {label, url, ok, status}} for every topic, cached for 12 hours per version."""
    hit = _CACHE.get(version)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    links = {t: docs.link(t, version) for t in docs.TOPICS}
    with ThreadPoolExecutor(max_workers=6) as pool:
        probes = dict(zip(links, pool.map(lambda l: _probe(l["url"]), links.values())))
    result = {t: {**links[t], **probes[t]} for t in links}
    _CACHE[version] = (time.time(), result)
    return result


def annotate(report: dict, version: str) -> None:
    """Mark each finding's docs link as verified (reachable) or not, and fall back to the overview page."""
    try:
        status = check(version)
    except Exception:  # never let a docs outage block an analysis
        report["docs_check"] = {"checked": False}
        return
    ok = sum(1 for s in status.values() if s["ok"])
    report["docs_check"] = {"checked": True, "reachable": ok, "total": len(status),
                            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for f in report["findings"]:
        s = status.get(f["docs"]["topic"])
        f["docs"]["verified"] = bool(s and s["ok"])
