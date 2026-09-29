// Client-side Excel and PDF exports, used when there's no server (the browser demo).
// The server builds richer versions with openpyxl and ReportLab.
import type { Report } from "../api/types";

export async function reportToXlsx(r: Report): Promise<Blob> {
  const XLSX = await import("xlsx");
  const wb = XLSX.utils.book_new();
  const s = r.summary;
  const summary: (string | number)[][] = [
    ["File", r.file_name],
    ["Rule set", r.rule_set.name],
    ["Tosca docs version", r.docs_version],
    ["Analyzed", new Date(r.created_at).toLocaleString()],
    ["Compliance score", s.score],
    ["Score after fixing high findings", s.projected_score],
    ["Test cases", s.test_cases],
    ["Steps", s.steps],
    ["Findings", s.findings],
    [],
    ["Category", "Score", "Findings"],
    ...r.categories.map((c) => [c.label, c.score, c.findings]),
  ];
  if (r.execution) {
    summary.splice(9, 0, ["Runs passed / failed / not run", `${r.execution.passed} / ${r.execution.failed} / ${r.execution.not_run}`],
      ["Failures traced to a finding", r.execution.failures_traced]);
  }
  const ws1 = XLSX.utils.aoa_to_sheet(summary);
  ws1["!cols"] = [{ wch: 34 }, { wch: 40 }, { wch: 10 }];
  XLSX.utils.book_append_sheet(wb, ws1, "Summary");

  const findings = r.findings.map((f) => ({
    Severity: f.severity, Rule: f.rule_id, Title: f.title, Location: f.location,
    Occurrences: f.occurrences.length, "Linked failed runs": f.linked_failures.length,
    "Why it matters": f.message, Current: f.current, Suggested: f.suggested, "Tosca docs": f.docs.url,
  }));
  const ws2 = XLSX.utils.json_to_sheet(findings);
  ws2["!cols"] = [8, 9, 42, 44, 12, 12, 50, 36, 36, 50].map((wch) => ({ wch }));
  XLSX.utils.book_append_sheet(wb, ws2, "Findings");

  const occ = r.findings.flatMap((f) =>
    f.occurrences.map((o) => ({ Rule: f.rule_id, Severity: f.severity, "Test case": o.test_case, Location: o.location, Detail: o.detail })),
  );
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(occ), "Occurrences");

  if (r.results.length) {
    const runs = r.results.map((x) => ({
      "Test case": x.name, Result: x.status.replace("_", " "), Message: x.message,
      "Linked findings": r.findings.filter((f) => x.test_case_id && f.linked_failures.includes(x.test_case_id)).map((f) => f.rule_id).join(", "),
    }));
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(runs), "Execution");
  }
  const out = XLSX.write(wb, { type: "array", bookType: "xlsx" }) as ArrayBuffer;
  return new Blob([out], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

// jsPDF's built-in fonts only cover Latin-1, so swap the few typographic characters we use.
const latin = (t: string) => t.replace(/›/g, ">").replace(/[–—]/g, "-").replace(/[“”]/g, '"').replace(/•/g, "*").replace(/×/g, "x");

export async function reportToPdf(r: Report): Promise<Blob> {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const W = 210, M = 18, CW = W - 2 * M;
  let y = 20;
  const need = (h: number) => {
    if (y + h > 280) { doc.addPage(); y = 18; }
  };
  const text = (t: string, size: number, opts: { bold?: boolean; color?: [number, number, number]; font?: string; width?: number } = {}) => {
    doc.setFont(opts.font ?? "helvetica", opts.bold ? "bold" : "normal");
    doc.setFontSize(size);
    doc.setTextColor(...(opts.color ?? [27, 29, 34]));
    const lines = doc.splitTextToSize(latin(t), opts.width ?? CW) as string[];
    need(lines.length * size * 0.42);
    doc.text(lines, M, y);
    y += lines.length * size * 0.42 + 1.5;
  };

  text(r.file_name, 20, { bold: true });
  text(`${r.rule_set.name} · Tosca docs ${r.docs_version} · Analyzed ${new Date(r.created_at).toLocaleString()}`, 8, { color: [91, 95, 104] });
  y += 2;
  doc.setFillColor(27, 29, 34);
  doc.roundedRect(M, y, 54, 26, 2, 2, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(28);
  doc.text(String(r.summary.score), M + 5, y + 16);
  doc.setFontSize(9);
  doc.text("/ 100 compliance", M + 24, y + 16);
  doc.setTextColor(27, 29, 34);
  doc.setFont("helvetica", "normal");
  const s = r.summary;
  doc.text([`${s.test_cases} test cases · ${s.steps} steps · ${s.findings} findings`,
    s.high_findings ? `Fixing the ${s.high_findings} high findings raises this to about ${s.projected_score}.` : "No high-severity findings."],
    M + 60, y + 10);
  y += 34;

  text("By category", 12, { bold: true });
  for (const c of r.categories) {
    need(7);
    doc.setFontSize(9);
    doc.text(latin(c.label), M, y);
    doc.setFillColor(230, 226, 218);
    doc.rect(M + 62, y - 3, 90, 3, "F");
    doc.setFillColor(...((c.score >= 70 ? [31, 63, 168] : [184, 72, 28]) as [number, number, number]));
    doc.rect(M + 62, y - 3, 0.9 * c.score, 3, "F");
    doc.text(String(c.score), M + 158, y);
    y += 6;
  }
  if (r.execution) {
    y += 2;
    text("Execution results", 12, { bold: true });
    text(`Passed ${r.execution.passed} · Failed ${r.execution.failed} · Not run ${r.execution.not_run}. ${r.execution.failures_traced} of ${r.execution.failed} failures trace back to a finding.`, 9);
  }
  y += 3;
  text("Findings and suggested fixes", 12, { bold: true });
  const sevColor: Record<string, [number, number, number]> = { high: [184, 72, 28], medium: [192, 122, 30], low: [31, 63, 168] };
  for (const f of r.findings) {
    need(40);
    y += 2;
    text(`${f.severity.toUpperCase()}  ${f.rule_id}${f.linked_failures.length ? `  ·  linked to ${f.linked_failures.length} failed run(s)` : ""}`, 8, { bold: true, color: sevColor[f.severity] });
    text(f.title, 10.5, { bold: true });
    text(f.location, 8, { color: [91, 95, 104] });
    text(f.message, 9);
    const cur = doc.splitTextToSize(latin("CURRENT\n" + f.current), CW / 2 - 6) as string[];
    const sug = doc.splitTextToSize(latin("SUGGESTED\n" + f.suggested), CW / 2 - 6) as string[];
    const h = Math.max(cur.length, sug.length) * 3.4 + 5;
    need(h);
    doc.setFillColor(251, 241, 235);
    doc.rect(M, y - 3, CW / 2 - 1, h, "F");
    doc.setFillColor(237, 241, 250);
    doc.rect(M + CW / 2 + 1, y - 3, CW / 2 - 1, h, "F");
    doc.setFont("courier", "normal");
    doc.setFontSize(8);
    doc.setTextColor(27, 29, 34);
    doc.text(cur, M + 3, y + 1);
    doc.text(sug, M + CW / 2 + 4, y + 1);
    y += h + 1;
    text(`Tosca docs: ${f.docs.label} — ${f.docs.url}`, 7.5, { color: [31, 63, 168] });
  }
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setFontSize(7);
    doc.setTextColor(91, 95, 104);
    doc.text(latin(`Tosca Analyzer · ${r.file_name}`), M, 290);
    doc.text(`Page ${i} of ${pages}`, W - M, 290, { align: "right" });
  }
  return doc.output("blob");
}
