"""Parse Tosca exports (.tsu workspace subsets, XML exports, Excel sheets) into the model.

Tosca export formats differ between versions and export paths, so the parser is
deliberately tolerant: it recognises objects by element name *or* by a type
attribute (Type / ObjectClass / xsi:type), reads fields from attributes *or*
child elements, and ignores containers it doesn't know. If your exports use a
different vocabulary, extend the KIND_ALIASES table below.
"""
from __future__ import annotations

import gzip
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from .model import ReusableBlock, StepValue, TestCase, TestStep, Workspace
from . import xlsx_reader


class ParseError(Exception):
    """Raised with a message that can be shown to the user as-is."""


KIND_ALIASES = {
    "testcase": {"testcase", "xtestcase", "scriptedtestcase"},
    "step": {"teststep", "xteststep", "moduleteststep"},
    "stepfolder": {"teststepfolder", "xteststepfolder", "conditionfolder", "loopfolder"},
    "reference": {
        "teststepfolderreference", "reusableteststepblockreference",
        "reuseableteststepblockreference", "teststepblockreference", "rtbreference",
    },
    "value": {"teststepvalue", "xteststepvalue"},
    "block": {"reusableteststepblock", "reuseableteststepblock", "teststepblock", "rtb"},
    "folder": {"testcasefolder", "tcfolder", "folder", "testcasesfolder", "component"},
    "param": {"testconfigurationparameter", "configurationparameter", "tcparameter", "tcp"},
    "recovery": {"recoveryscenario", "recoveryscenariocollection"},
    "cleanup": {"cleanupscenario"},
    "businessparam": {"businessparameter", "parameter"},
    "property": {"property", "attribute"},
}
_KIND_LOOKUP = {alias: kind for kind, aliases in KIND_ALIASES.items() for alias in aliases}
TYPE_ATTRS = ("type", "objectclass", "class", "{http://www.w3.org/2001/xmlschema-instance}type")
TRUE = {"true", "1", "yes", "y"}
ISSUE_KEY = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")


# ---------------------------------------------------------------- helpers

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _attrs(el: ET.Element) -> dict[str, str]:
    return {k.rsplit("}", 1)[-1].lower() if "}" in k else k.lower(): v for k, v in el.attrib.items()}


def _get(el: ET.Element, *keys: str, default: str = "") -> str:
    """Field lookup: attribute (case-insensitive) first, then a direct child element's text."""
    attrs = _attrs(el)
    for key in keys:
        if key.lower() in attrs:
            return attrs[key.lower()]
    for key in keys:
        for child in el:
            if _local(child.tag) == key.lower() and len(child) == 0:
                return (child.text or "").strip()
    return default


def _kind(el: ET.Element) -> str:
    attrs = _attrs(el)
    for key in ("type", "objectclass", "class"):
        if key in attrs:
            k = _KIND_LOOKUP.get(attrs[key].rsplit(".", 1)[-1].lower())
            if k:
                return k
    return _KIND_LOOKUP.get(_local(el.tag), "")


def _flag(el: ET.Element, *keys: str) -> bool:
    return _get(el, *keys).strip().lower() in TRUE


def _disabled(el: ET.Element) -> bool:
    if _flag(el, "Disabled", "IsDisabled"):
        return True
    enabled = _get(el, "Enabled").strip().lower()
    return enabled in {"false", "0", "no"}


# ---------------------------------------------------------------- entry points

def unwrap(data: bytes) -> tuple[bytes, str]:
    """Peel gzip / zip wrappers. Returns (payload, detected container)."""
    if data[:2] == b"\x1f\x8b":
        try:
            return unwrap(gzip.decompress(data))[0], "gzip"
        except OSError as exc:
            raise ParseError(f"The file looks compressed but could not be unpacked ({exc}).") from exc
    if data[:2] == b"PK":
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        if "xl/workbook.xml" in names:
            return data, "xlsx"
        xmls = [n for n in names if n.lower().endswith((".xml", ".tsu", ".tcs"))]
        if not xmls:
            raise ParseError("The archive contains no XML export. Export the subset as XML from Tosca and try again.")
        biggest = max(xmls, key=lambda n: zf.getinfo(n).file_size)
        return unwrap(zf.read(biggest))[0], "zip"
    return data, "raw"


def parse_bytes(data: bytes, filename: str) -> Workspace:
    payload, container = unwrap(data)
    name = re.sub(r"\.(tsu|xml|xlsx|zip)$", "", filename, flags=re.I) or "Workspace"
    if container == "xlsx" or filename.lower().endswith(".xlsx"):
        ws = parse_xlsx(payload, name)
        ws.source_format = "xlsx"
        return ws
    text = payload.lstrip(b"\xef\xbb\xbf").strip()
    if not text.startswith(b"<"):
        raise ParseError(
            "This file isn't in a format the analyzer can read yet. In Tosca Commander, export the "
            "TestCase folder as XML (or a workspace subset), then upload that file."
        )
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ParseError(f"The XML is malformed: {exc}. Re-export the file from Tosca and try again.") from exc
    ws = parse_tree(root, name)
    ws.source_format = "tsu" if filename.lower().endswith(".tsu") else "xml"
    if not ws.test_cases:
        raise ParseError("No test cases were found in this file. Check that the export includes a TestCase folder.")
    return ws


# ---------------------------------------------------------------- XML

class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def next(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n}"


def parse_tree(root: ET.Element, name: str) -> Workspace:
    ws = Workspace(name=_get(root, "Name", default=name) or name)
    ids = _Ids()

    def walk(el: ET.Element, path: list[str]) -> None:
        for child in el:
            kind = _kind(child)
            cname = _get(child, "Name")
            if kind == "testcase":
                ws.test_cases.append(_parse_testcase(child, path, ids))
            elif kind == "block":
                ws.blocks.append(_parse_block(child, ids))
            elif kind == "folder":
                walk(child, path + ([cname] if cname else []))
            elif kind == "param":
                ws.config_params[cname] = _get(child, "Value")
                walk(child, path)  # CP containers may nest further parameters
            elif kind == "recovery":
                if _local(child.tag) != "recoveryscenariocollection" and cname:
                    ws.recovery_scenarios.append(cname)
                walk(child, path)
            elif kind == "cleanup":
                if cname:
                    ws.cleanup_scenarios.append(cname)
            else:
                walk(child, path)

    walk(root, [])
    return ws


def _parse_values(el: ET.Element, prefix: str = "") -> list[StepValue]:
    out: list[StepValue] = []
    for child in el:
        kind = _kind(child)
        if kind == "value":
            vname = _get(child, "Name")
            full = f"{prefix}.{vname}" if prefix else vname
            nested = [c for c in child if _kind(c) == "value"]
            own_value = _get(child, "Value")
            if not nested or own_value:
                out.append(StepValue(
                    name=full,
                    value=own_value,
                    action_mode=_get(child, "ActionMode", default="Input") or "Input",
                    data_type=_get(child, "DataType", default="String") or "String",
                    disabled=_disabled(child),
                ))
            if nested:
                out.extend(_parse_values(child, full))
        elif kind == "businessparam":
            out.append(StepValue(name=_get(child, "Name"), value=_get(child, "Value"), action_mode="Input"))
        elif kind == "" and _local(child.tag) in {"values", "teststepvalues", "parameters", "businessparameters"}:
            out.extend(_parse_values(child, prefix))
    return out


def _parse_steps(el: ET.Element, folder_path: list[str], ids: _Ids, disabled: bool, out: list[TestStep]) -> None:
    for child in el:
        kind = _kind(child)
        cname = _get(child, "Name")
        if kind == "step":
            out.append(TestStep(
                id=_get(child, "Id", "UniqueId", default="") or ids.next("S"),
                name=cname or "Unnamed step",
                kind="step",
                module=_get(child, "Module", "ModuleName", "ModuleReference"),
                values=_parse_values(child),
                disabled=disabled or _disabled(child),
                folder_path=list(folder_path),
            ))
        elif kind == "reference":
            target = _get(child, "Reference", "ReusedBlock", "ReusedItem", "Target", "Block") or cname
            out.append(TestStep(
                id=_get(child, "Id", "UniqueId", default="") or ids.next("S"),
                name=cname or target,
                kind="reference",
                module="",
                reference=target,
                values=_parse_values(child),
                disabled=disabled or _disabled(child),
                folder_path=list(folder_path),
            ))
        elif kind == "stepfolder":
            _parse_steps(child, folder_path + [cname or "Folder"], ids, disabled or _disabled(child), out)
        elif kind in {"", "folder"} and len(child):
            _parse_steps(child, folder_path, ids, disabled, out)


def _parse_properties(el: ET.Element) -> dict[str, str]:
    props: dict[str, str] = {}
    for child in el.iter():
        if _kind(child) == "property":
            key = _get(child, "Name", "Key")
            if key:
                props[key] = _get(child, "Value")
    for key in ("JiraKey", "Issue", "IssueKey", "Requirement", "ExternalId", "Ticket", "Owner", "Priority", "State"):
        v = _get(el, key)
        if v:
            props.setdefault(key, v)
    return props


def _parse_testcase(el: ET.Element, path: list[str], ids: _Ids) -> TestCase:
    tc = TestCase(
        id=_get(el, "Id", "UniqueId", default="") or ids.next("TC"),
        name=_get(el, "Name") or "Unnamed test case",
        path=list(path),
        description=_get(el, "Description"),
        properties=_parse_properties(el),
    )
    _parse_steps(el, [], ids, _disabled(el), tc.steps)
    for i, s in enumerate(tc.steps, 1):
        s.index = i
    keys: list[str] = []
    for k, v in tc.properties.items():
        if re.search(r"jira|issue|requirement|ticket|external|rally|story", k, re.I):
            keys += ISSUE_KEY.findall(v) or ([v] if re.match(r"^(US|TC|DE)\d+$", v) else [])
    keys += ISSUE_KEY.findall(tc.name)
    tc.requirement_keys = sorted(set(keys))
    return tc


def _parse_block(el: ET.Element, ids: _Ids) -> ReusableBlock:
    params = []
    for child in el.iter():
        if _kind(child) == "businessparam" and _local(child.tag) != "parameters":
            n = _get(child, "Name")
            if n:
                params.append(n)
    block = ReusableBlock(
        id=_get(el, "Id", "UniqueId", default="") or ids.next("B"),
        name=_get(el, "Name") or "Unnamed block",
        parameters=params,
    )
    _parse_steps(el, [], ids, False, block.steps)
    for i, s in enumerate(block.steps, 1):
        s.index = i
    return block


# ---------------------------------------------------------------- Excel test case sheets

_COLS = {
    "testcase": ("test case", "testcase", "test case name", "tc"),
    "folder": ("folder", "path", "component"),
    "step": ("test step", "teststep", "step", "step name"),
    "module": ("module",),
    "value_name": ("value name", "attribute", "field", "control"),
    "value": ("value", "data", "input"),
    "action": ("actionmode", "action mode", "action"),
    "description": ("description",),
    "issue": ("jira", "issue", "requirement", "jira key"),
}


def _pick(row: dict[str, str], key: str) -> str:
    lowered = {k.strip().lower(): v for k, v in row.items()}
    for alias in _COLS[key]:
        if alias in lowered:
            return str(lowered[alias]).strip()
    return ""


def parse_xlsx(data: bytes, name: str) -> Workspace:
    sheets = xlsx_reader.read_sheets(data)
    ws = Workspace(name=name)
    tcs: dict[str, TestCase] = {}
    ids = _Ids()
    for rows in sheets.values():
        for row in xlsx_reader.table_dicts(rows):
            tc_name = _pick(row, "testcase")
            if not tc_name:
                continue
            tc = tcs.get(tc_name)
            if tc is None:
                folder = _pick(row, "folder")
                tc = TestCase(id=ids.next("TC"), name=tc_name,
                              path=[p.strip() for p in re.split(r"[/>›\\]", folder) if p.strip()] if folder else [],
                              description=_pick(row, "description"))
                issue = _pick(row, "issue")
                if issue:
                    tc.properties["JiraKey"] = issue
                    tc.requirement_keys = ISSUE_KEY.findall(issue)
                tcs[tc_name] = tc
                ws.test_cases.append(tc)
            step_name = _pick(row, "step") or _pick(row, "module") or "Step"
            if not tc.steps or tc.steps[-1].name != step_name:
                tc.steps.append(TestStep(id=ids.next("S"), name=step_name, module=_pick(row, "module"),
                                         index=len(tc.steps) + 1))
            vname = _pick(row, "value_name")
            if vname:
                tc.steps[-1].values.append(StepValue(name=vname, value=_pick(row, "value"),
                                                     action_mode=_pick(row, "action") or "Input"))
    if not ws.test_cases:
        raise ParseError("No test cases found. The sheet needs at least a 'Test Case' column and a header row.")
    return ws
