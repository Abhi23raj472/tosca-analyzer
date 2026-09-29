import { useEffect, useState } from "react";
import { errText, fmtDateTime, useApp } from "../app-context";
import type { AnalysisSummary } from "../api/types";
import { Spinner, Trash } from "../components/Icons";

export default function History() {
  const { backend, go, toast, bump, version } = useApp();
  const [items, setItems] = useState<AnalysisSummary[] | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);

  useEffect(() => {
    backend.analyses().then(setItems).catch((e) => { toast(errText(e)); setItems([]); });
  }, [backend, version, toast]);

  const remove = async (id: string) => {
    await backend.deleteAnalysis(id);
    setConfirm(null);
    bump();
    toast("Analysis deleted");
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">History</p>
          <h1 className="h1" style={{ fontSize: "clamp(28px, 3.6vw, 40px)" }}>Past analyses</h1>
          <p className="lead">Open a report to see its findings again, compare scores between runs, or export it.</p>
        </div>
        <button className="btn btn-primary" onClick={() => go("new")}>New analysis</button>
      </div>
      <div className="panel" style={{ overflowX: "auto" }}>
        {!items ? (
          <div className="empty"><div className="row" style={{ justifyContent: "center" }}><Spinner /> Loading…</div></div>
        ) : items.length === 0 ? (
          <div className="empty"><h3 className="h3">No analyses yet</h3>Upload a Tosca export to create the first one.</div>
        ) : (
          <table className="list-table">
            <thead>
              <tr>
                <th>File</th><th className="num">Score</th><th className="hide-sm">Rule set</th>
                <th className="num hide-sm">Test cases</th><th className="num">Findings</th><th className="num hide-sm">Failed runs</th>
                <th className="hide-sm">Analyzed</th><th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id} className="clickable" onClick={() => go("report", a.id)}>
                  <td className="mono" style={{ fontWeight: 500 }}>{a.file_name}</td>
                  <td className="num" style={{ fontWeight: 700, color: a.score >= 70 ? "var(--blue)" : "var(--rust)" }}>{a.score}</td>
                  <td className="hide-sm">{a.rule_set}</td>
                  <td className="num hide-sm">{a.test_cases}</td>
                  <td className="num">{a.findings}{a.high_findings ? <span className="muted"> · {a.high_findings} high</span> : null}</td>
                  <td className="num hide-sm">{a.failed_runs ?? "—"}</td>
                  <td className="hide-sm muted">{fmtDateTime(a.created_at)}</td>
                  <td onClick={(e) => e.stopPropagation()} style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                    {a.id === "sample-claims" ? <span className="muted small">Sample</span> : confirm === a.id ? (
                      <span className="row" style={{ gap: 6, justifyContent: "flex-end", flexWrap: "nowrap" }}>
                        <button className="btn btn-sm" onClick={() => setConfirm(null)}>Keep</button>
                        <button className="btn btn-sm btn-primary" onClick={() => remove(a.id)}>Delete</button>
                      </span>
                    ) : (
                      <button className="iconbtn" aria-label={`Delete ${a.file_name}`} onClick={() => setConfirm(a.id)}><Trash /></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
