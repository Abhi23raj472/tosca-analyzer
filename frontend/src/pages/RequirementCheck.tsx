import { useCallback, useEffect, useState } from "react";
import { errText, useApp } from "../app-context";
import type { AnalysisSummary, CheckResult, Issue, Report, RowStatus } from "../api/types";
import { copyText } from "../lib/download";
import { Alert, Bulb, Check, Spinner } from "../components/Icons";

const LABEL: Record<RowStatus, string> = { matched: "Matched", partial: "Partial", mismatch: "Mismatch", missing: "Missing", extra: "Extra" };

function parseManual(steps: string, ac: string): Pick<Issue, "steps" | "acceptance_criteria"> {
  const clean = (l: string) => l.replace(/^\s*(\d+[.)]|[-*•])\s*/, "").trim();
  return {
    steps: steps.split("\n").map(clean).filter(Boolean).map((l) => {
      const [action, ...rest] = l.split(/\s*(?:->|→|=>|\|)\s*/);
      return { action, expected: rest.join(" ").trim() };
    }),
    acceptance_criteria: ac.split("\n").map(clean).filter(Boolean),
  };
}

export default function RequirementCheck() {
  const { backend, toast, lastReportId, version } = useApp();
  const [source, setSource] = useState<"jira" | "rally">("jira");
  const [key, setKey] = useState(backend.mode === "demo" ? "CLM-1482" : "");
  const [manual, setManual] = useState(false);
  const [manualSteps, setManualSteps] = useState("");
  const [manualAc, setManualAc] = useState("");
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([]);
  const [analysisId, setAnalysisId] = useState<string>("");
  const [report, setReport] = useState<Report | null>(null);
  const [tcId, setTcId] = useState("");
  const [autoMatched, setAutoMatched] = useState(false);
  const [issue, setIssue] = useState<Issue | null>(null);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [onlyGaps, setOnlyGaps] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jiraSite, setJiraSite] = useState("");

  useEffect(() => {
    backend.analyses().then((list) => {
      setAnalyses(list);
      setAnalysisId((cur) => cur || lastReportId || list[0]?.id || "");
    });
    backend.settings().then((s) => setJiraSite(source === "jira" ? s.jira.base_url : s.rally.api_key ? s.rally.base_url : ""));
  }, [backend, version, lastReportId, source]);

  useEffect(() => {
    if (!analysisId) return;
    backend.analysis(analysisId).then(setReport).catch(() => setReport(null));
  }, [backend, analysisId]);

  const runCheck = useCallback(async (iss: Issue, rep: Report, testCase: string) => {
    if (!testCase) return;
    setBusy("check");
    setError(null);
    try {
      setResult(await backend.checkRequirement(rep.id, testCase, iss));
    } catch (e) {
      setError(errText(e));
      setResult(null);
    } finally {
      setBusy(null);
    }
  }, [backend]);

  const fetchIssue = async () => {
    if (!report) {
      setError("Analyze a Tosca export first, then compare it with a ticket.");
      return;
    }
    setError(null);
    setResult(null);
    let iss: Issue;
    if (manual) {
      const parsed = parseManual(manualSteps, manualAc);
      if (!parsed.steps.length) {
        setError("Paste at least one step, one per line, as “Action -> Expected result”.");
        return;
      }
      iss = { source: "manual", key: key.trim().toUpperCase() || "Pasted steps", summary: "Steps pasted by hand", status: "", type: "Manual",
        steps_source: "manual", warnings: [], ...parsed };
    } else {
      if (!key.trim()) return;
      setBusy("fetch");
      try {
        iss = await backend.fetchIssue(source, key.trim());
      } catch (e) {
        setError(errText(e));
        setBusy(null);
        return;
      }
      setBusy(null);
    }
    setIssue(iss);
    let target = tcId;
    const matched = await backend.matchTestCase(report.id, iss.key).catch(() => null);
    if (matched) {
      target = matched;
      setTcId(matched);
      setAutoMatched(true);
    } else {
      setAutoMatched(false);
    }
    if (!target) {
      setError(`No test case stores ${iss.key} as its issue key. Pick the Tosca test case to compare.`);
      return;
    }
    if (!iss.steps.length) {
      setError(`${iss.key} has no manual test steps. Add steps to the ticket (Xray, Zephyr or a numbered list in the description), or paste them here.`);
      return;
    }
    runCheck(iss, report, target);
  };

  // Open in a working state: in the preview, compare the sample ticket straight away.
  useEffect(() => {
    const hasSampleCase = report?.test_cases.some((t) => t.requirement_keys.includes("CLM-1482"));
    if (backend.mode === "demo" && hasSampleCase && !issue && key === "CLM-1482") fetchIssue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report]);

  const post = async () => {
    if (!result) return;
    setBusy("post");
    try {
      const r = await backend.postResult(result.id);
      toast(`Result posted to ${r.issue}`);
    } catch (e) {
      toast(errText(e));
    } finally {
      setBusy(null);
    }
  };

  const copy = async () => {
    if (!result) return;
    toast((await copyText(result.comment)) ? "Result copied" : "Copy isn't allowed here. Select the text in the summary instead.");
  };

  const rows = result?.rows.filter((r) => !onlyGaps || r.status !== "matched") ?? [];
  const gaps = result ? result.rows.filter((r) => r.status !== "matched").length : 0;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Requirement check</p>
          <h1 className="h1" style={{ fontSize: "clamp(26px, 3.4vw, 40px)" }}>Is the Tosca test built the way the ticket says?</h1>
          <p className="lead" style={{ maxWidth: "80ch" }}>
            Pulls the manual test steps from a JIRA issue (Xray or Zephyr test) or a Rally test case, lines them up with the Tosca
            test case, and flags every gap.
          </p>
        </div>
        {result && issue && (
          <div className="row">
            <button className="btn" onClick={copy}>Copy result</button>
            {issue.source !== "manual" && (
              <button className="btn btn-primary" onClick={post} disabled={busy === "post"}>
                {busy === "post" && <Spinner />} Post result to {issue.key}
              </button>
            )}
          </div>
        )}
      </div>

      <div className="req-grid">
        <aside className="stack">
          <div className="panel panel-pad stack">
            <div className="seg" role="group" aria-label="Ticket source">
              <button aria-pressed={source === "jira" && !manual} onClick={() => { setSource("jira"); setManual(false); }}>JIRA</button>
              <button aria-pressed={source === "rally" && !manual} onClick={() => { setSource("rally"); setManual(false); }}>Rally</button>
            </div>
            <div>
              <label className="label" htmlFor="issue-key">{manual ? "Ticket key (optional)" : source === "jira" ? "JIRA issue key" : "Rally ID"}</label>
              <form className="row" style={{ flexWrap: "nowrap" }} onSubmit={(e) => { e.preventDefault(); fetchIssue(); }}>
                <input id="issue-key" className="input mono" value={key} onChange={(e) => setKey(e.target.value)}
                  placeholder={source === "jira" ? "CLM-1482" : "TC1234 or US5678"} autoComplete="off" />
                <button className="btn btn-blue" type="submit" disabled={!!busy || (!manual && !key.trim())}>
                  {busy === "fetch" || busy === "check" ? <Spinner /> : manual ? "Compare" : "Fetch"}
                </button>
              </form>
              <div className="hint">
                {manual ? "Compares the steps below instead of fetching them." :
                  source === "jira" ? "A story or a test issue. Linked tests are pulled in too." : "A test case, or a user story with a linked test case."}
              </div>
            </div>
            <div>
              <label className="label" htmlFor="analysis">Analysis</label>
              <select id="analysis" className="select" value={analysisId} onChange={(e) => { setAnalysisId(e.target.value); setTcId(""); setResult(null); }}>
                {analyses.length === 0 && <option value="">No analyses yet</option>}
                {analyses.map((a) => <option key={a.id} value={a.id}>{a.file_name}</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="testcase">Tosca test case</label>
              <select id="testcase" className="select" value={tcId}
                onChange={(e) => { setTcId(e.target.value); setAutoMatched(false); if (issue && report) runCheck(issue, report, e.target.value); }}>
                <option value="">Choose a test case…</option>
                {report?.test_cases.map((t) => <option key={t.id} value={t.id}>{t.breadcrumb}</option>)}
              </select>
              <div className="hint">{autoMatched ? "Auto-matched by the issue key stored on the test case." : "Matched automatically when a test case stores the issue key."}</div>
            </div>
            {!manual && (
              <div className="conn">
                <i style={{ background: jiraSite ? "var(--blue)" : "var(--muted)" }} />
                {backend.mode === "demo" ? "Preview: sample ticket CLM-1482 only" : jiraSite ? `Connected to ${jiraSite.replace(/^https?:\/\//, "")}` : "Not connected. Add credentials in Settings."}
              </div>
            )}
            <button className="linkbtn small" style={{ textAlign: "left" }} onClick={() => setManual(!manual)}>
              {manual ? "Fetch from JIRA or Rally instead" : "Paste steps by hand instead"}
            </button>
            {manual && (
              <>
                <div>
                  <label className="label" htmlFor="manual-steps">Expected steps</label>
                  <textarea id="manual-steps" className="textarea" value={manualSteps} onChange={(e) => setManualSteps(e.target.value)}
                    placeholder={"1. Log in as a claims member -> Dashboard is shown\n2. Open \"New claim\" -> Empty claim form"} />
                  <div className="hint">{"One step per line: action, then “->”, then the expected result."}</div>
                </div>
                <div>
                  <label className="label" htmlFor="manual-ac">Acceptance criteria (optional)</label>
                  <textarea id="manual-ac" className="textarea" style={{ minHeight: 90 }} value={manualAc} onChange={(e) => setManualAc(e.target.value)}
                    placeholder={"- Member can submit a claim\n- New claims show status \"Pending review\""} />
                </div>
              </>
            )}
          </div>

          {issue && (
            <div className="panel panel-pad">
              <div className="row" style={{ gap: 8 }}>
                <span className="keychip">{issue.key}</span>
                <span className="muted small">{[issue.type, issue.status].filter(Boolean).join(" · ")}</span>
              </div>
              <h3 className="h3" style={{ fontSize: 17, margin: "12px 0 14px", fontFamily: "var(--font-body)", fontWeight: 600 }}>{issue.summary}</h3>
              {issue.linked_test && <p className="muted small">Steps from linked test {issue.linked_test}.</p>}
              {result && result.criteria.length > 0 && (
                <>
                  <div className="eyebrow" style={{ color: "var(--muted)", margin: 0 }}>
                    Acceptance criteria covered · {result.criteria_covered} of {result.criteria.length}
                  </div>
                  <ul className="ac">
                    {result.criteria.map((c) => (
                      <li key={c.text}>
                        <span style={{ color: c.covered ? "var(--blue)" : "var(--rust)" }}>{c.covered ? <Check /> : <Alert />}</span>
                        <span>{c.text}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </aside>

        <section style={{ minWidth: 0 }}>
          {error && <div className="error" role="alert" style={{ marginBottom: 16 }}>{error}</div>}
          {result ? (
            <>
              <div className="tiles">
                <div className="tile-dark">
                  <span>Design match</span>
                  <div className="num" style={{ fontFamily: "var(--font-display)", fontWeight: 800 }}>{result.design_match} / {result.expected_steps}</div>
                  <span>expected steps fully covered</span>
                </div>
                {(Object.keys(LABEL) as RowStatus[]).map((k) => (
                  <div className="panel tile" key={k}>
                    <span className={`badge st-${k}`}>{LABEL[k]}</span>
                    <div className="num">{result.counts[k]}</div>
                  </div>
                ))}
              </div>
              <div className="panel">
                <div className="row" style={{ padding: "18px 20px", justifyContent: "space-between" }}>
                  <h2 className="h3">Step-by-step comparison</h2>
                  <div className="pills">
                    <button className="pill" aria-pressed={!onlyGaps} onClick={() => setOnlyGaps(false)}>All steps</button>
                    <button className="pill" aria-pressed={onlyGaps} onClick={() => setOnlyGaps(true)}>Only gaps ({gaps})</button>
                  </div>
                </div>
                <div className="table-wrap">
                  <table className="cmp">
                    <thead>
                      <tr><th>#</th><th>Expected · {issue?.source === "rally" ? "Rally" : issue?.source === "manual" ? "Ticket" : "JIRA"}</th><th>Built · Tosca</th><th>Result</th></tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <FragmentRow key={i} r={r} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <details style={{ marginTop: 16 }}>
                <summary className="muted small" style={{ cursor: "pointer" }}>Result text for the ticket</summary>
                <pre className="code code-sug" style={{ marginTop: 8 }}>{result.comment}</pre>
              </details>
            </>
          ) : busy === "check" || busy === "fetch" ? (
            <div className="panel empty"><div className="row" style={{ justifyContent: "center" }}><Spinner /> Comparing steps…</div></div>
          ) : (
            <div className="panel empty">
              <h3 className="h3">Compare a ticket with its Tosca test</h3>
              {analyses.length ? "Enter an issue key and fetch it. The test case that stores that key is picked automatically." :
                "Analyze a Tosca export first. Its test cases become available here."}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function FragmentRow({ r }: { r: CheckResult["rows"][number] }) {
  return (
    <>
      <tr>
        <td className="n">{r.n ?? "+"}</td>
        <td>
          <div style={{ fontWeight: 500 }}>{r.action}</div>
          <div className="exp">Expect: {r.expected || "—"}</div>
        </td>
        <td className="built">{r.built.length ? r.built.join("\n") : "— no matching step —"}</td>
        <td><span className={`badge st-${r.status}`}>{LABEL[r.status]}</span></td>
      </tr>
      {r.hint && (
        <tr className="hint-row">
          <td />
          <td colSpan={3}><div className="bulb"><Bulb /><span>{r.hint}</span></div></td>
        </tr>
      )}
    </>
  );
}
