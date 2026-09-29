"""JIRA integration: fetch manual test steps (Xray / Zephyr Scale / description) and post results.

Supported step sources:
  xray_cloud     Xray Cloud GraphQL API (needs Xray client id + secret)
  xray_server    Xray Server / Data Center REST API (/rest/raven/1.0)
  zephyr_scale   Zephyr Scale Cloud API (needs a Zephyr API token)
  description    Numbered steps in the issue description ("1. Do X -> Expect Y")
  auto           Try the ones that are configured, then fall back to the description
"""
from __future__ import annotations

import html
import re

import httpx

TIMEOUT = httpx.Timeout(20.0)


class IntegrationError(Exception):
    """Message is safe to show to the user."""


def _client(cfg: dict) -> httpx.Client:
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise IntegrationError("JIRA isn't connected. Add your JIRA site URL and API token in Settings.")
    if cfg.get("deployment") == "server":
        headers = {"Authorization": f"Bearer {cfg.get('api_token', '')}"}
        return httpx.Client(base_url=base, headers=headers, timeout=TIMEOUT)
    return httpx.Client(base_url=base, auth=(cfg.get("email", ""), cfg.get("api_token", "")), timeout=TIMEOUT)


def _api(cfg: dict) -> str:
    return "/rest/api/2" if cfg.get("deployment") == "server" else "/rest/api/3"


def _check(resp: httpx.Response, what: str) -> dict | list:
    if resp.status_code == 401:
        raise IntegrationError("JIRA rejected the credentials. Check the email and API token in Settings.")
    if resp.status_code == 403:
        raise IntegrationError(f"Your JIRA account can't read {what}.")
    if resp.status_code == 404:
        raise IntegrationError(f"{what} wasn't found in JIRA.")
    if resp.status_code >= 400:
        raise IntegrationError(f"JIRA returned {resp.status_code} for {what}.")
    return resp.json()


# ---------------------------------------------------------------- text helpers

def adf_text(node) -> str:
    """Flatten Atlassian Document Format (JIRA Cloud rich text) into plain text with line breaks."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_text(n) for n in node)
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    inner = adf_text(node.get("content", []))
    if t in {"paragraph", "heading", "listItem", "tableRow"}:
        return inner.strip() + "\n"
    if t == "hardBreak":
        return "\n"
    if t == "orderedList":
        items = [adf_text(i).strip() for i in node.get("content", [])]
        return "".join(f"{n}. {i}\n" for n, i in enumerate(items, 1))
    if t == "bulletList":
        return "".join(f"- {adf_text(i).strip()}\n" for i in node.get("content", []))
    if t == "tableCell" or t == "tableHeader":
        return inner.strip() + " | "
    return inner


def strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text or "", flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


STEP_LINE = re.compile(r"^\s*(?:\d+[.)]|step\s*\d+[:.)]?|[-*•])\s+(?P<body>.+)$", re.I)
SPLIT_EXPECT = re.compile(r"\s*(?:->|→|=>|\|\s*|;\s*expect(?:ed)?(?: result)?:?|\s+expect(?:ed)?(?: result)?:)\s*", re.I)


def steps_from_text(text: str) -> tuple[list[dict], list[str]]:
    """Parse '1. Action -> Expected' lines and an 'Acceptance criteria' bullet list from free text."""
    steps: list[dict] = []
    criteria: list[str] = []
    section = "steps"
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower().rstrip(":")
        if low.startswith("acceptance criteria"):
            section = "ac"
            continue
        if re.match(r"^(test )?steps?$|^steps to reproduce$", low):
            section = "steps"
            continue
        m = STEP_LINE.match(line)
        if not m:
            continue
        body = m.group("body").strip()
        if section == "ac":
            criteria.append(body)
        else:
            parts = [p.strip(" |") for p in SPLIT_EXPECT.split(body, maxsplit=1)]
            steps.append({"action": parts[0], "expected": parts[1] if len(parts) > 1 else ""})
    return steps, criteria


# ---------------------------------------------------------------- step sources

def _xray_server(cfg: dict, key: str) -> list[dict]:
    with _client(cfg) as c:
        data = _check(c.get(f"/rest/raven/1.0/api/test/{key}/step"), f"Xray steps for {key}")
    out = []
    for s in data if isinstance(data, list) else data.get("steps", []):
        def raw(field):
            v = s.get(field) or s.get("fields", {}).get(field.capitalize())
            return strip_html(v.get("raw") if isinstance(v, dict) else (v or ""))
        action = raw("step") or raw("action")
        data_val = raw("data")
        out.append({"action": f"{action} ({data_val})" if data_val else action, "expected": raw("result")})
    return out


def _xray_cloud(cfg: dict, key: str) -> list[dict]:
    if not (cfg.get("xray_client_id") and cfg.get("xray_client_secret")):
        raise IntegrationError("Xray Cloud needs a client ID and secret in Settings.")
    with httpx.Client(base_url="https://xray.cloud.getxray.app/api/v2", timeout=TIMEOUT) as c:
        auth = c.post("/authenticate", json={"client_id": cfg["xray_client_id"], "client_secret": cfg["xray_client_secret"]})
        if auth.status_code >= 400:
            raise IntegrationError("Xray Cloud rejected the client ID and secret.")
        token = auth.json()
        query = ('query($jql: String) { getTests(jql: $jql, limit: 1) { results { '
                 'steps { action data result } } } }')
        resp = c.post("/graphql", json={"query": query, "variables": {"jql": f'key = "{key}"'}},
                      headers={"Authorization": f"Bearer {token}"})
        data = _check(resp, f"Xray test {key}")
    results = (((data.get("data") or {}).get("getTests") or {}).get("results") or [])
    if not results:
        return []
    return [{"action": s.get("action", "") + (f" ({s['data']})" if s.get("data") else ""),
             "expected": s.get("result", "")} for s in results[0].get("steps", [])]


def _zephyr_scale(cfg: dict, key: str) -> list[dict]:
    if not cfg.get("zephyr_token"):
        raise IntegrationError("Zephyr Scale needs an API token in Settings.")
    headers = {"Authorization": f"Bearer {cfg['zephyr_token']}"}
    with httpx.Client(base_url="https://api.zephyrscale.smartbear.com/v2", headers=headers, timeout=TIMEOUT) as c:
        tc_key = key
        if not re.search(r"-T\d+$", key):  # a story key: find its linked Zephyr test case
            links = _check(c.get(f"/issuelinks/{key}/testcases"), f"Zephyr test cases linked to {key}")
            if not links:
                return []
            tc_key = links[0].get("key")
        data = _check(c.get(f"/testcases/{tc_key}/teststeps", params={"maxResults": 200}), f"Zephyr steps for {tc_key}")
    out = []
    for item in data.get("values", []):
        inline = item.get("inline") or {}
        out.append({"action": strip_html(inline.get("description", "")) +
                    (f" ({strip_html(inline['testData'])})" if inline.get("testData") else ""),
                    "expected": strip_html(inline.get("expectedResult", ""))})
    return out


def fetch_issue(cfg: dict, key: str) -> dict:
    key = key.strip().upper()
    if not re.match(r"^[A-Z][A-Z0-9]+-(T)?\d+$", key):
        raise IntegrationError(f"'{key}' doesn't look like a JIRA issue key (for example CLM-1482).")
    fields = "summary,status,issuetype,description,issuelinks"
    if cfg.get("acceptance_field"):
        fields += "," + cfg["acceptance_field"]
    with _client(cfg) as c:
        issue = _check(c.get(f"{_api(cfg)}/issue/{key}", params={"fields": fields}), f"Issue {key}")
    f = issue.get("fields", {})
    desc = f.get("description")
    desc_text = adf_text(desc) if isinstance(desc, dict) else strip_html(desc or "")
    desc_steps, desc_ac = steps_from_text(desc_text)

    source = cfg.get("test_steps_source") or "auto"
    order = {"auto": ["xray_cloud", "xray_server", "zephyr_scale"], "description": []}.get(source, [source])
    steps: list[dict] = []
    used = "description"
    errors: list[str] = []
    for src in order:
        if src == "xray_cloud" and source == "auto" and not cfg.get("xray_client_id"):
            continue
        if src == "zephyr_scale" and source == "auto" and not cfg.get("zephyr_token"):
            continue
        if src == "xray_server" and source == "auto" and cfg.get("deployment") != "server":
            continue
        try:
            steps = {"xray_cloud": _xray_cloud, "xray_server": _xray_server, "zephyr_scale": _zephyr_scale}[src](cfg, key)
        except IntegrationError as exc:
            errors.append(str(exc))
            steps = []
        if steps:
            used = src
            break

    linked_from = None
    if not steps and source in {"auto", "xray_cloud", "xray_server"}:
        # A story: pull steps from the first linked Test issue.
        for link in f.get("issuelinks", []):
            other = link.get("outwardIssue") or link.get("inwardIssue") or {}
            if (other.get("fields", {}).get("issuetype", {}).get("name", "").lower() == "test") and other.get("key"):
                try:
                    linked = fetch_issue({**cfg, "test_steps_source": source}, other["key"])
                except IntegrationError:
                    continue
                if linked["steps"]:
                    steps, used, linked_from = linked["steps"], linked["steps_source"], other["key"]
                    break
    if not steps:
        steps = desc_steps

    ac_raw = f.get(cfg.get("acceptance_field") or "", None)
    if isinstance(ac_raw, dict):
        _, ac = steps_from_text("Acceptance criteria\n" + adf_text(ac_raw))
    elif isinstance(ac_raw, str) and ac_raw:
        _, ac = steps_from_text("Acceptance criteria\n" + strip_html(ac_raw))
    else:
        ac = desc_ac

    return {
        "source": "jira", "key": key, "summary": f.get("summary", ""),
        "status": (f.get("status") or {}).get("name", ""), "type": (f.get("issuetype") or {}).get("name", ""),
        "steps": steps, "acceptance_criteria": ac, "steps_source": used, "linked_test": linked_from,
        "url": f"{cfg['base_url'].rstrip('/')}/browse/{key}",
        "warnings": errors if not steps else [],
    }


def post_comment(cfg: dict, key: str, text: str) -> str:
    if cfg.get("deployment") == "server":
        body = {"body": text}
    else:
        paragraphs = [{"type": "paragraph", "content": [{"type": "text", "text": line}]} for line in text.split("\n") if line]
        body = {"body": {"type": "doc", "version": 1, "content": paragraphs}}
    with _client(cfg) as c:
        data = _check(c.post(f"{_api(cfg)}/issue/{key}/comment", json=body), f"Issue {key}")
    return str(data.get("id", ""))
