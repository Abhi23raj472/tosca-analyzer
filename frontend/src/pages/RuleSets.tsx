import { useEffect, useMemo, useState, type ReactNode } from "react";
import { errText, useApp } from "../app-context";
import type { Catalog, RuleSet, Severity } from "../api/types";
import { Spinner } from "../components/Icons";

const PARAM_LABELS: Record<string, string> = {
  pattern: "Name must match (regex)",
  max_steps: "Max steps",
  min_steps: "From steps",
  min_length: "Min copied steps",
  min_test_cases: "Min test cases",
  high_at: "High from",
};

export default function RuleSets() {
  const { backend, toast } = useApp();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [sets, setSets] = useState<RuleSet[]>([]);
  const [selected, setSelected] = useState<string>("tricentis-default");
  const [draft, setDraft] = useState<RuleSet | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const reload = (select?: string) =>
    backend.ruleSets().then((s) => {
      setSets(s);
      const pick = s.find((x) => x.id === (select ?? selected)) ?? s[0];
      setSelected(pick.id);
      setDraft(structuredClone(pick));
    });

  useEffect(() => {
    backend.catalog().then(setCatalog);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backend]);

  const byCat = useMemo(() => {
    const m = new Map<string, Catalog["rules"]>();
    catalog?.rules.forEach((r) => m.set(r.category, [...(m.get(r.category) ?? []), r]));
    return m;
  }, [catalog]);

  if (!catalog || !draft) return <div className="loading-screen"><div className="row"><Spinner /> Loading rules…</div></div>;
  const locked = draft.id === "tricentis-default";

  const setRule = (id: string, patch: Partial<RuleSet["rules"][string]>) =>
    setDraft({ ...draft, rules: { ...draft.rules, [id]: { ...draft.rules[id], ...patch } } });

  const duplicate = () => {
    const copy: RuleSet = { ...structuredClone(draft), id: `new-${Date.now()}`, name: `${draft.name} (team copy)`, builtin: false };
    setSets([...sets, copy]);
    setSelected(copy.id);
    setDraft(copy);
  };

  const save = async () => {
    setSaving(true);
    try {
      const saved = await backend.saveRuleSet(draft);
      await reload(saved.id);
      toast("Rule set saved");
    } catch (e) {
      toast(errText(e));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!draft.id.startsWith("new-")) await backend.deleteRuleSet(draft.id);
    setConfirmDelete(false);
    await reload("tricentis-default");
    toast("Rule set deleted");
  };

  const enabled = Object.values(draft.rules).filter((r) => r.enabled).length;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Rule sets</p>
          <h1 className="h1" style={{ fontSize: "clamp(28px, 3.6vw, 40px)" }}>Choose what gets checked</h1>
          <p className="lead">Start from the Tricentis best practices and tune severities and thresholds to your team's standards.</p>
        </div>
      </div>
      <div className="rules-layout">
        <aside className="stack" style={{ gap: 4 }}>
          {sets.map((s) => (
            <button key={s.id} className="rs-item" aria-current={s.id === selected}
              onClick={() => { setSelected(s.id); setDraft(structuredClone(s)); setConfirmDelete(false); }}>
              <div style={{ fontWeight: 600 }}>{s.name}</div>
              <div className="muted small">{Object.values(s.rules).filter((r) => r.enabled).length} rules{s.id === "tricentis-default" ? " · built in" : ""}</div>
            </button>
          ))}
          <button className="btn btn-sm" style={{ marginTop: 10 }} onClick={duplicate}>Duplicate selected</button>
        </aside>

        <section className="panel" style={{ minWidth: 0 }}>
          <div className="panel-pad" style={{ borderBottom: "1px solid var(--line)" }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div style={{ flex: "1 1 280px", minWidth: 0 }}>
                <label className="label" htmlFor="rs-name">Name</label>
                <input id="rs-name" className="input" value={draft.name} disabled={locked} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </div>
              <div className="row" style={{ alignSelf: "flex-end" }}>
                {!locked && (confirmDelete ? (
                  <>
                    <span className="small muted">Delete this rule set?</span>
                    <button className="btn btn-sm" onClick={() => setConfirmDelete(false)}>Keep</button>
                    <button className="btn btn-sm btn-primary" onClick={remove}>Delete</button>
                  </>
                ) : <button className="btn" onClick={() => setConfirmDelete(true)}>Delete</button>)}
                {!locked && <button className="btn btn-primary" onClick={save} disabled={saving || !draft.name.trim()}>{saving && <Spinner />} Save</button>}
              </div>
            </div>
            <p className="hint" style={{ marginBottom: 0 }}>
              {locked ? "The built-in set follows Tricentis guidance and can't be edited. Duplicate it to make a team version." : `${enabled} of ${catalog.rules.length} rules on.`}
            </p>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="list-table" style={{ minWidth: 640 }}>
              <thead><tr><th style={{ width: 60 }}>On</th><th>Rule</th><th style={{ width: 130 }}>Severity</th></tr></thead>
              <tbody>
                {catalog.categories.map((c) => (
                  <CategoryRows key={c.key} label={c.label}>
                    {(byCat.get(c.key) ?? []).map((r) => {
                      const cfg = draft.rules[r.id] ?? { enabled: true, severity: r.severity, params: r.params };
                      return (
                        <tr key={r.id} className={`rule-row${cfg.enabled ? "" : " off"}`}>
                          <td>
                            <input id={`rule-${r.id}`} type="checkbox" style={{ width: 18, height: 18, accentColor: "var(--blue)" }}
                              checked={cfg.enabled} disabled={locked} onChange={(e) => setRule(r.id, { enabled: e.target.checked })}
                              aria-label={`Enable ${r.name}`} />
                          </td>
                          <td>
                            <div><span className="rule-id">{r.id}</span> <strong style={{ fontWeight: 600 }}>{r.name}</strong></div>
                            <div className="muted small">{r.description}</div>
                            {Object.keys(r.params).map((p) => (
                              <label className="param" key={p}>
                                {PARAM_LABELS[p] ?? p}
                                <input id={`param-${r.id}-${p}`} className="input" disabled={locked}
                                  value={String(cfg.params?.[p] ?? r.params[p] ?? "")}
                                  onChange={(e) => setRule(r.id, { params: { ...cfg.params, [p]: typeof r.params[p] === "number" ? Number(e.target.value) || 0 : e.target.value } })} />
                              </label>
                            ))}
                          </td>
                          <td>
                            <select id={`sev-${r.id}`} className="select" style={{ padding: "6px 8px" }} value={cfg.severity} disabled={locked}
                              onChange={(e) => setRule(r.id, { severity: e.target.value as Severity })} aria-label={`Severity for ${r.name}`}>
                              <option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </CategoryRows>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}

function CategoryRows({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <tr><td colSpan={3} style={{ background: "var(--surface-2)", fontWeight: 600, fontSize: 13, padding: "10px 16px" }}>{label}</td></tr>
      {children}
    </>
  );
}
