import { useEffect, useRef, useState } from "react";
import { errText, fmtDate, useApp } from "../app-context";
import type { AnalysisSummary, Catalog, RuleSet, Settings } from "../api/types";
import { Arrow, Close, FileIcon, Refresh, Upload } from "../components/Icons";
import sampleXml from "../demo/Claims_Regression.xml?raw";
import sampleRun from "../demo/Claims_Run.xml?raw";

type Kind = "tests" | "results";
const ACCEPT: Record<Kind, string> = { tests: ".tsu,.xml,.xlsx,.zip", results: ".xml,.xlsx,.pdf" };

export default function NewAnalysis() {
  const { backend, go, toast, bump, version } = useApp();
  const [kind, setKind] = useState<Kind>("tests");
  const [tests, setTests] = useState<File | null>(null);
  const [results, setResults] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [ruleSets, setRuleSets] = useState<RuleSet[]>([]);
  const [ruleSetId, setRuleSetId] = useState("tricentis-default");
  const [cats, setCats] = useState<string[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [recent, setRecent] = useState<AnalysisSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    Promise.all([backend.catalog(), backend.ruleSets(), backend.settings()]).then(([c, rs, s]) => {
      setCatalog(c);
      setRuleSets(rs);
      setSettings(s);
      setCats(c.categories.map((x) => x.key).filter((k) => k !== "documentation"));
    }).catch((e) => setError(errText(e)));
  }, [backend]);

  useEffect(() => {
    backend.analyses().then((a) => setRecent(a.slice(0, 3))).catch(() => setRecent([]));
  }, [backend, version]);

  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => setProgress((p) => Math.min(92, p + (92 - p) * 0.12)), 250);
    return () => window.clearInterval(t);
  }, [busy]);

  const ruleSet = ruleSets.find((r) => r.id === ruleSetId);
  const enabledCount = ruleSet ? Object.values(ruleSet.rules).filter((r) => r.enabled).length : 20;

  const take = (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    setError(null);
    if (f.size > 200 * 1024 * 1024) {
      setError(`${f.name} is larger than 200 MB. Export a smaller workspace subset.`);
      return;
    }
    const ok = kind === "tests" ? /\.(tsu|xml|xlsx|zip)$/i.test(f.name) : /\.(xml|xlsx|pdf)$/i.test(f.name);
    if (!ok) {
      setError(kind === "tests" ? "Upload a .tsu, .xml or .xlsx test case export." : "Upload execution results as .xml, .xlsx or .pdf.");
      return;
    }
    if (kind === "tests") setTests(f);
    else setResults(f);
  };

  const useSample = () => {
    setTests(new File([sampleXml], "Claims_Regression.xml", { type: "text/xml" }));
    setResults(new File([sampleRun], "Claims_Run.xml", { type: "text/xml" }));
    setError(null);
    toast("Sample test cases and a nightly run are loaded");
  };

  const run = async () => {
    if (!tests) return;
    setBusy(true);
    setProgress(8);
    setError(null);
    try {
      const report = await backend.analyze({ file: tests, results, ruleSetId, categories: cats }, setStage);
      setProgress(100);
      bump();
      go("report", report.id);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
      setStage("");
    }
  };

  const toggleCat = (k: string) => setCats((c) => (c.includes(k) ? c.filter((x) => x !== k) : [...c, k]));
  const current = kind === "tests" ? tests : results;

  return (
    <div className="page">
      <div className="split">
        <section>
          <p className="eyebrow">Step 1 of 2</p>
          <h1 className="h1">Check your Tosca test cases against Tricentis guidance</h1>
          <p className="lead">
            Upload a workspace subset or an execution result. Every rule points to the Tosca documentation, and each
            finding comes with a suggested fix.
          </p>

          <div className="kind-tabs" role="group" aria-label="What are you uploading?">
            <button className="kind-tab" aria-pressed={kind === "tests"} onClick={() => setKind("tests")}>
              <strong>Test case export</strong>
              <span>Workspace subset (.tsu), XML or Excel</span>
            </button>
            <button className="kind-tab" aria-pressed={kind === "results"} onClick={() => setKind("results")}>
              <strong>Execution results {results && "✓"}</strong>
              <span>Run results as XML, Excel or PDF</span>
            </button>
          </div>

          <div
            className={`drop${over ? " over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files); }}
            onClick={() => input.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
            aria-label={kind === "tests" ? "Upload test case export" : "Upload execution results"}
          >
            <span style={{ color: "var(--blue)" }}><Upload /></span>
            <h3>{current ? "Drop a different file" : "Drop your file here"}</h3>
            <div className="muted">
              or <span className="linkbtn">browse your computer</span>
            </div>
            <div className="formats">
              {kind === "tests" ? "Accepts .tsu · .xml · .xlsx · max 200 MB" : "Optional · links failures to findings · .xml · .xlsx · .pdf"}
            </div>
            <input id="upload-input" ref={input} type="file" hidden accept={ACCEPT[kind]} onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
          </div>

          {[tests, results].map((f, i) => f && (
            <div className="panel filerow" key={i}>
              <FileIcon />
              <div className="grow">
                <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
                  <span className="name">{f.name}</span>
                  <span className="muted small">
                    {busy ? `${stage || "Parsing"} · ${Math.round(progress)}%` : `${i === 0 ? "Test cases" : "Execution results"} · ${(f.size / 1024).toFixed(0)} KB`}
                  </span>
                </div>
                {busy && <div className="progress"><i style={{ width: `${progress}%` }} /></div>}
              </div>
              <button className="iconbtn" aria-label={`Remove ${f.name}`} onClick={() => (i === 0 ? setTests(null) : setResults(null))} disabled={busy}>
                <Close />
              </button>
            </div>
          ))}

          {error && <div className="error" style={{ marginTop: 16 }} role="alert">{error}</div>}

          {!tests && (
            <p className="muted small" style={{ marginTop: 18 }}>
              No export handy? <button className="linkbtn" onClick={useSample}>Load the sample claims suite</button> (48 test cases plus a nightly run).
            </p>
          )}
        </section>

        <aside>
          <div className="panel panel-pad stack">
            <h2 className="h3" style={{ fontSize: 21 }}>Analysis settings</h2>
            <div>
              <label className="label" htmlFor="rule-set">Rule set</label>
              <select id="rule-set" className="select" value={ruleSetId} onChange={(e) => setRuleSetId(e.target.value)}>
                {ruleSets.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} ({Object.values(r.rules).filter((x) => x.enabled).length} rules)
                  </option>
                ))}
              </select>
            </div>
            <div>
              <span className="label">Check categories</span>
              {catalog?.categories.map((c) => (
                <label className="check" key={c.key}>
                  <input id={`cat-${c.key}`} type="checkbox" checked={cats.includes(c.key)} onChange={() => toggleCat(c.key)} />
                  {c.label}
                </label>
              ))}
            </div>
            <div className="docs-box">
              <strong><Refresh /> Documentation source</strong>
              Findings link to Tricentis Tosca {settings?.docs_version ?? "2026.1"} documentation
              {backend.mode === "server" && settings?.docs_live_check ? ", and links are checked at analysis time." : "."}
            </div>
            <button className="btn btn-primary btn-lg" onClick={run} disabled={!tests || busy || cats.length === 0}>
              {busy ? "Analyzing…" : <>Analyze {tests ? "test cases" : ""} <Arrow /></>}
            </button>
            {!tests && <span className="hint" style={{ marginTop: -8 }}>Add a test case export to start. {enabledCount} rules are on.</span>}
          </div>

          {recent.length > 0 && (
            <div className="recent">
              <span className="label" style={{ margin: 0, color: "var(--muted)", fontWeight: 500 }}>Recent analyses</span>
              {recent.map((a) => (
                <button key={a.id} className="panel recent-item" onClick={() => go("report", a.id)}>
                  <div className="grow">
                    <div className="mono" style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis" }}>{a.file_name}</div>
                    <div className="muted small">{fmtDate(a.created_at)} · {a.findings} findings</div>
                  </div>
                  <span className="score-mini" style={{ color: a.score >= 70 ? "var(--blue)" : "var(--rust)" }}>{a.score}</span>
                </button>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
