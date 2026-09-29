import { useEffect, useMemo, useRef, useState } from "react";
import { errText, fmtDate, useApp } from "../app-context";
import type { Finding, Report, Severity } from "../api/types";
import { saveFile } from "../lib/download";
import { Book, Chevron, Spinner } from "../components/Icons";

type Filter = "all" | Severity;

export default function ReportPage({ id }: { id: string }) {
  const { backend, go, toast } = useApp();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [exporting, setExporting] = useState<string | null>(null);
  const resultsInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setReport(null);
    backend.analysis(id).then(setReport).catch((e) => setError(errText(e)));
  }, [backend, id]);

  const failedNames = useMemo(() => {
    const m = new Map<string, string>();
    report?.results.forEach((r) => r.status === "failed" && r.test_case_id && m.set(r.test_case_id, r.message));
    return m;
  }, [report]);

  if (error) return <div className="page"><div className="error">{error}</div></div>;
  if (!report) return <div className="loading-screen"><div className="row"><Spinner /> Loading report…</div></div>;

  const s = report.summary;
  const shown = report.findings.filter((f) => filter === "all" || f.severity === filter);
  const counts = { all: report.findings.length, ...s.by_severity };

  const doExport = async (fmt: "xlsx" | "pdf") => {
    setExporting(fmt);
    try {
      const { filename, data } = await backend.exportFile(report, fmt);
      toast(await saveFile(filename, data));
    } catch (e) {
      toast(errText(e));
    } finally {
      setExporting(null);
    }
  };

  const attach = async (f: File | undefined) => {
    if (!f) return;
    try {
      setReport(await backend.attachResults(report.id, f));
      toast("Execution results linked to findings");
    } catch (e) {
      toast(errText(e));
    }
  };

  return (
    <div className="page">
      <button className="back" onClick={() => go("new")}>← New analysis</button>
      <div className="page-head">
        <div>
          <h1 className="h1" style={{ fontSize: "clamp(28px, 3.6vw, 40px)", overflowWrap: "anywhere" }}>{report.file_name}</h1>
          <div className="meta">
            {report.sample ? "Sample report · " : ""}
            {report.rule_set.name} ({report.rule_set.rules_run} rules) · Docs version {report.docs_version} · Analyzed {fmtDate(report.created_at)}
          </div>
        </div>
        <div className="row">
          <button className="btn" onClick={() => doExport("xlsx")} disabled={!!exporting}>
            {exporting === "xlsx" ? <Spinner /> : null} Export Excel
          </button>
          <button className="btn btn-primary" onClick={() => doExport("pdf")} disabled={!!exporting}>
            {exporting === "pdf" ? <Spinner /> : null} Export PDF
          </button>
        </div>
      </div>

      {report.warnings.length > 0 && (
        <div className="warn" style={{ marginBottom: 20 }}>{report.warnings.join(" ")}</div>
      )}

      <div className="summary-grid">
        <div className="scorecard">
          <div className="label-sm">COMPLIANCE SCORE</div>
          <div className="score">{s.score}<small>/ 100</small></div>
          <p>
            {s.high_findings
              ? `Fixing the ${s.high_findings} high-severity finding${s.high_findings > 1 ? "s" : ""} would raise this to about ${s.projected_score}.`
              : "No high-severity findings. Work through the medium ones next."}
          </p>
          <div className="facts">
            <span><b>{s.test_cases}</b>test cases</span>
            <span><b>{s.steps}</b>steps</span>
            <span><b>{s.findings}</b>findings</span>
          </div>
        </div>

        <div className="panel panel-pad">
          <h2 className="h3">By category</h2>
          <div className="bars">
            {report.categories.map((c) => (
              <div className="bar-row" key={c.key}>
                <span>{c.label}</span>
                <div className="bar" role="img" aria-label={`${c.label}: ${c.score} of 100`}>
                  <i style={{ width: `${c.score}%`, background: c.score >= 70 ? "var(--blue)" : "var(--rust)" }} />
                </div>
                <span className="bar-val">{c.score}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel panel-pad">
          <h2 className="h3">Execution results</h2>
          {report.execution ? (
            <>
              <div className="stackbar" role="img"
                aria-label={`${report.execution.passed} passed, ${report.execution.failed} failed, ${report.execution.not_run} not run`}>
                <i style={{ width: `${(report.execution.passed / report.execution.total) * 100}%`, background: "var(--blue)" }} />
                <i style={{ width: `${(report.execution.failed / report.execution.total) * 100}%`, background: "var(--rust)" }} />
                <i style={{ width: `${(report.execution.not_run / report.execution.total) * 100}%`, background: "var(--muted)" }} />
              </div>
              <div className="legend-row"><i className="dot" style={{ background: "var(--blue)" }} />Passed<b>{report.execution.passed}</b></div>
              <div className="legend-row"><i className="dot" style={{ background: "var(--rust)" }} />Failed<b>{report.execution.failed}</b></div>
              <div className="legend-row"><i className="dot" style={{ background: "var(--muted)" }} />Not run<b>{report.execution.not_run}</b></div>
              <p className="muted small" style={{ margin: "12px 0 0" }}>
                {report.execution.failed
                  ? `${report.execution.failures_traced} of ${report.execution.failed} failures trace back to a finding below.`
                  : "No failed runs in this execution."}
                {report.execution.unmatched ? ` ${report.execution.unmatched} results didn't match a test case.` : ""}
              </p>
            </>
          ) : (
            <>
              <p className="muted small">Add a run to see which failures trace back to a finding.</p>
              {backend.mode === "server" ? (
                <>
                  <button className="btn btn-sm" onClick={() => resultsInput.current?.click()}>Add execution results</button>
                  <input id="attach-results" ref={resultsInput} type="file" hidden accept=".xml,.xlsx,.pdf" onChange={(e) => attach(e.target.files?.[0])} />
                </>
              ) : (
                <p className="muted small">Upload the results together with the test cases on the New analysis screen.</p>
              )}
            </>
          )}
        </div>
      </div>

      <div className="page-head" style={{ marginBottom: 18, alignItems: "center" }}>
        <h2 className="h2" style={{ fontSize: 27 }}>Findings &amp; suggested fixes</h2>
        <div className="pills" role="group" aria-label="Filter by severity">
          {(["all", "high", "medium", "low"] as Filter[]).map((f) => (
            <button key={f} className="pill" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {f === "all" ? "All" : f[0].toUpperCase() + f.slice(1)} ({counts[f]})
            </button>
          ))}
        </div>
      </div>

      {shown.length === 0 ? (
        <div className="panel empty"><h3 className="h3">Nothing at this severity</h3>Pick another filter to see the rest.</div>
      ) : (
        shown.map((f) => <FindingCard key={f.rule_id + f.title} f={f} failed={failedNames} />)
      )}
    </div>
  );
}

function FindingCard({ f, failed }: { f: Finding; failed: Map<string, string> }) {
  const [open, setOpen] = useState(false);
  const n = f.occurrences.length;
  return (
    <article className="panel finding">
      <div className="finding-head">
        <div>
          <div className="row" style={{ gap: 10 }}>
            <span className={`badge sev-${f.severity}`}>{f.severity[0].toUpperCase() + f.severity.slice(1)}</span>
            <span className="rule-id">{f.rule_id}</span>
            {f.linked_failures.length > 0 && <span className="linked">Linked to {f.linked_failures.length} failed run(s)</span>}
          </div>
          <h3>{f.title}</h3>
          <div className="loc">{f.location}</div>
        </div>
        <a className="chip" href={f.docs.url} target="_blank" rel="noreferrer" title={f.docs.url}>
          <Book /> Tosca docs · {f.docs.label}
        </a>
      </div>
      <p className="msg">{f.message}</p>
      <div className="diff">
        <div className="code code-cur"><span className="tag">CURRENT</span>{f.current}</div>
        <div className="code code-sug"><span className="tag">SUGGESTED</span>{f.suggested}</div>
      </div>
      {n > 1 && (
        <>
          <button className="btn btn-ghost btn-sm" style={{ marginTop: 12, paddingLeft: 0 }} onClick={() => setOpen(!open)} aria-expanded={open}>
            <Chevron open={open} /> {open ? "Hide" : "Show"} all {n} occurrences
          </button>
          {open && (
            <ul className="occ-list">
              {f.occurrences.map((o, i) => (
                <li key={i}>
                  <span>{o.location}</span>
                  <span className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
                    <span className="muted">{o.detail}</span>
                    {o.test_case_id && failed.has(o.test_case_id) && <span className="failed" title={failed.get(o.test_case_id)}>Failed run</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </article>
  );
}
