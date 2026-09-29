import { useEffect, useState, type FormEvent } from "react";
import { errText, useApp } from "../app-context";
import type { Settings } from "../api/types";
import { Spinner } from "../components/Icons";

export default function SettingsPage() {
  const { backend, toast } = useApp();
  const [s, setS] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  const demo = backend.mode === "demo";

  useEffect(() => {
    backend.settings().then(setS).catch((e) => toast(errText(e)));
  }, [backend, toast]);

  if (!s) return <div className="loading-screen"><div className="row"><Spinner /> Loading settings…</div></div>;

  const jira = (patch: Partial<Settings["jira"]>) => setS({ ...s, jira: { ...s.jira, ...patch } });
  const rally = (patch: Partial<Settings["rally"]>) => setS({ ...s, rally: { ...s.rally, ...patch } });

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      setS(await backend.saveSettings(s));
      toast("Settings saved");
    } catch (err) {
      toast(errText(err));
    } finally {
      setSaving(false);
    }
  };

  const field = (id: string, label: string, value: string, onChange: (v: string) => void, opts: { type?: string; hint?: string; placeholder?: string } = {}) => (
    <div>
      <label className="label" htmlFor={id}>{label}</label>
      <input id={id} className="input" type={opts.type ?? "text"} value={value} placeholder={opts.placeholder} disabled={demo}
        autoComplete="off" onChange={(e) => onChange(e.target.value)} />
      {opts.hint && <div className="hint">{opts.hint}</div>}
    </div>
  );

  return (
    <form className="page" onSubmit={save}>
      <div className="page-head">
        <div>
          <p className="eyebrow">Settings</p>
          <h1 className="h1" style={{ fontSize: "clamp(28px, 3.6vw, 40px)" }}>Connections and documentation</h1>
          <p className="lead">Tokens are stored on the server and never sent back to the browser.</p>
        </div>
        <button className="btn btn-primary" type="submit" disabled={saving}>{saving && <Spinner />} Save settings</button>
      </div>
      {demo && <div className="warn" style={{ marginBottom: 20 }}>This preview has no server, so JIRA and Rally can't be connected here. Run the server to use them.</div>}

      <div className="stack" style={{ gap: 20 }}>
        <section className="panel panel-pad stack">
          <div>
            <h2 className="section-title">Tricentis documentation</h2>
            <p className="muted small" style={{ margin: 0 }}>Every finding links to the matching page for your Tosca version.</p>
          </div>
          <div className="form-grid">
            <div>
              <label className="label" htmlFor="docs-version">Tosca version</label>
              <select id="docs-version" className="select" value={s.docs_version} onChange={(e) => setS({ ...s, docs_version: e.target.value })}>
                {["2026.1", "2025.2", "2025.1", "2024.2", "2024.1", "16.0"].map((v) => <option key={v}>{v}</option>)}
              </select>
            </div>
            <label className="check" style={{ alignSelf: "end" }}>
              <input id="docs-live" type="checkbox" checked={s.docs_live_check} disabled={demo} onChange={(e) => setS({ ...s, docs_live_check: e.target.checked })} />
              Check each documentation link at analysis time
            </label>
          </div>
        </section>

        <section className="panel panel-pad stack">
          <div>
            <h2 className="section-title">JIRA</h2>
            <p className="muted small" style={{ margin: 0 }}>Used by the requirement check to read test steps and post results.</p>
          </div>
          <div className="form-grid">
            {field("jira-url", "Site URL", s.jira.base_url, (v) => jira({ base_url: v }), { placeholder: "https://your-company.atlassian.net" })}
            <div>
              <label className="label" htmlFor="jira-deploy">Deployment</label>
              <select id="jira-deploy" className="select" value={s.jira.deployment} disabled={demo} onChange={(e) => jira({ deployment: e.target.value as "cloud" | "server" })}>
                <option value="cloud">JIRA Cloud (email + API token)</option>
                <option value="server">Server / Data Center (personal access token)</option>
              </select>
            </div>
            {s.jira.deployment === "cloud" && field("jira-email", "Account email", s.jira.email, (v) => jira({ email: v }))}
            {field("jira-token", s.jira.deployment === "cloud" ? "API token" : "Personal access token", s.jira.api_token, (v) => jira({ api_token: v }), { type: "password" })}
            <div>
              <label className="label" htmlFor="jira-steps">Where test steps live</label>
              <select id="jira-steps" className="select" value={s.jira.test_steps_source} disabled={demo} onChange={(e) => jira({ test_steps_source: e.target.value })}>
                <option value="auto">Detect automatically</option>
                <option value="xray_cloud">Xray Cloud</option>
                <option value="xray_server">Xray Server / Data Center</option>
                <option value="zephyr_scale">Zephyr Scale</option>
                <option value="description">Numbered list in the description</option>
              </select>
            </div>
            {field("jira-ac", "Acceptance criteria field", s.jira.acceptance_field, (v) => jira({ acceptance_field: v }), { placeholder: "customfield_10035", hint: "Leave empty to read the 'Acceptance criteria' section of the description." })}
            {(s.jira.test_steps_source === "xray_cloud" || s.jira.test_steps_source === "auto") && (
              <>
                {field("xray-id", "Xray client ID", s.jira.xray_client_id, (v) => jira({ xray_client_id: v }))}
                {field("xray-secret", "Xray client secret", s.jira.xray_client_secret, (v) => jira({ xray_client_secret: v }), { type: "password" })}
              </>
            )}
            {(s.jira.test_steps_source === "zephyr_scale" || s.jira.test_steps_source === "auto") &&
              field("zephyr-token", "Zephyr Scale API token", s.jira.zephyr_token, (v) => jira({ zephyr_token: v }), { type: "password" })}
          </div>
        </section>

        <section className="panel panel-pad stack">
          <div>
            <h2 className="section-title">Rally</h2>
            <p className="muted small" style={{ margin: 0 }}>Reads test case steps and posts results as a discussion.</p>
          </div>
          <div className="form-grid">
            {field("rally-url", "Server", s.rally.base_url, (v) => rally({ base_url: v }))}
            {field("rally-key", "API key", s.rally.api_key, (v) => rally({ api_key: v }), { type: "password" })}
          </div>
        </section>
      </div>
    </form>
  );
}
