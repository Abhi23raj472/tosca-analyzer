"""Minimal .xlsx reader using only the standard library (zip + XML).

Good enough for flat tables: test case sheets and execution result exports.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_sheets(data: bytes) -> dict[str, list[list[str]]]:
    """Return {sheet_name: rows}, each row a list of cell strings."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = set(zf.namelist())

    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))

    # Map sheet names to their part paths through the workbook relationships.
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = {}
    if "xl/_rels/workbook.xml.rels" in names:
        rroot = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rroot:
            target = rel.get("Target", "")
            target = target.lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            rels[rel.get("Id")] = target

    sheets: dict[str, list[list[str]]] = {}
    for i, sheet in enumerate(wb.findall("m:sheets/m:sheet", _NS)):
        rid = sheet.get(f"{{{_REL_NS}}}id")
        path = rels.get(rid, f"xl/worksheets/sheet{i + 1}.xml")
        if path not in names:
            continue
        sroot = ET.fromstring(zf.read(path))
        rows: list[list[str]] = []
        for row in sroot.iter(f"{{{_NS['m']}}}row"):
            cells: dict[int, str] = {}
            for c in row.findall("m:c", _NS):
                ref = c.get("r")
                idx = _col_index(ref) if ref else len(cells)
                t = c.get("t")
                v = c.find("m:v", _NS)
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{{{_NS['m']}}}t"))
                else:
                    val = v.text if v is not None and v.text is not None else ""
                cells[idx] = val
            if cells:
                width = max(cells) + 1
                rows.append([cells.get(j, "") for j in range(width)])
            else:
                rows.append([])
        sheets[sheet.get("name", f"Sheet{i + 1}")] = rows
    return sheets


def table_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    """Treat the first non-empty row as a header and return dict rows."""
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return []
    header = [str(h).strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        out.append({header[i]: (r[i] if i < len(r) else "") for i in range(len(header)) if header[i]})
    return out
