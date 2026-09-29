// In-browser backend: the Python engine via Pyodide, history kept in this browser.
import type { Backend } from "./backend";
import type { AnalysisSummary, Catalog, CheckResult, Issue, Report, RuleSet, Settings } from "./types";
import { callEngine, startEngine } from "./pyodide";
import { reportToPdf, reportToXlsx } from "../lib/exporters";
import sampleReport from "../demo/sample-report.json";
import sampleIssue from "../demo/sample-issue.json";
import sampleCheck from "../demo/sample-check.json";
import rulesData from "../demo/rules.json";

const SAMPLE = sampleReport as unknown as Report;
const KEY = "tosca-analyzer:v1";

interface Store {
  reports: Report[];
  ruleSets: RuleSet[];
  settings: Partial<Settings>;
}

// Browser storage may be unavailable (private windows, previews); the demo then just forgets on reload.
let memory: Store = { reports: [], ruleSets: [], settings: {} };
function load(): Store {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) memory = { ...memory, ...JSON.parse(raw) };
  } catch { /* keep memory */ }
  return memory;
}
function save(next: Store) {
  memory = next;
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...next, reports: next.reports.slice(0, 8) }));
  } catch { /* quota or blocked: memory only */ }
}

const defaultRuleSet = (rulesData as { default_rule_set: RuleSet }).default_rule_set;
const DEFAULT_SETTINGS: Settings = {
  docs_version: "2026.1",
  docs_live_check: false,
  jira: { base_url: "", deployment: "cloud", email: "", api_token: "", test_steps_source: "auto", acceptance_field: "",
    xray_client_id: "", xray_client_secret: "", zephyr_token: "" },
  rally: { base_url: "https://rally1.rallydev.com", api_key: "", workspace: "" },
};

const summaryOf = (r: Report): AnalysisSummary => ({
  id: r.id, file_name: r.file_name, score: r.summary.score, rule_set: r.rule_set.name, created_at: r.created_at,
  test_cases: r.summary.test_cases, findings: r.summary.findings, high_findings: r.summary.high_findings,
  failed_runs: r.execution?.failed ?? null,
});

const uid = () => Math.random().toString(36).slice(2, 10);
const allReports = () => [...load().reports, SAMPLE];

export const demoBackend: Backend = {
  mode: "demo",
  async catalog() {
    return rulesData as unknown as Catalog;
  },
  async ruleSets() {
    return [defaultRuleSet, ...load().ruleSets];
  },
  async saveRuleSet(rs) {
    const s = load();
    const saved = { ...rs, id: rs.id && !rs.id.startsWith("new-") ? rs.id : `rs-${uid()}`, builtin: false };
    save({ ...s, ruleSets: [...s.ruleSets.filter((x) => x.id !== saved.id), saved] });
    return saved;
  },
  async deleteRuleSet(id) {
    const s = load();
    save({ ...s, ruleSets: s.ruleSets.filter((x) => x.id !== id) });
  },
  async settings() {
    const s = load().settings;
    return { ...DEFAULT_SETTINGS, ...s } as Settings;
  },
  async saveSettings(patch) {
    const s = load();
    save({ ...s, settings: { ...s.settings, docs_version: patch.docs_version ?? s.settings.docs_version } });
    return this.settings();
  },
  async analyze({ file, results, ruleSetId, categories }, onStage) {
    if (/\.pdf$/i.test(results?.name ?? "")) {
      throw new Error("Reading execution results from PDF needs the server. Upload the run as XML or Excel here.");
    }
    onStage?.("Starting the analysis engine");
    await startEngine().catch(() => undefined);
    onStage?.("Checking rules");
    const sets = await this.ruleSets();
    const rs = sets.find((x) => x.id === ruleSetId) ?? defaultRuleSet;
    const settings = await this.settings();
    const report = await callEngine<Report>(
      "analyze",
      { name: file.name, rule_set: rs, categories, docs_version: settings.docs_version, results_name: results?.name },
      results ? { path: file, results_path: results } : { path: file },
    );
    const full: Report = { ...report, id: `a-${uid()}`, created_at: new Date().toISOString() };
    const s = load();
    save({ ...s, reports: [full, ...s.reports] });
    return full;
  },
  async attachResults() {
    throw new Error("Upload the execution results together with the test cases in this preview.");
  },
  async analyses() {
    return allReports().map(summaryOf);
  },
  async analysis(id) {
    const r = allReports().find((x) => x.id === id);
    if (!r) throw new Error("That analysis is no longer stored in this browser.");
    return r;
  },
  async deleteAnalysis(id) {
    const s = load();
    save({ ...s, reports: s.reports.filter((r) => r.id !== id) });
  },
  async exportFile(report, fmt) {
    const base = report.file_name.replace(/\.[^.]+$/, "");
    return { filename: `${base}_analysis.${fmt}`, data: fmt === "xlsx" ? await reportToXlsx(report) : await reportToPdf(report) };
  },
  async fetchIssue(source, key) {
    if (source === "jira" && key.trim().toUpperCase() === (sampleIssue as Issue).key) return sampleIssue as Issue;
    throw new Error(
      `Fetching ${key || "tickets"} from ${source === "jira" ? "JIRA" : "Rally"} needs the Tosca Analyzer server with your credentials. ` +
        "In this preview, try CLM-1482 or paste the steps yourself.",
    );
  },
  async matchTestCase(analysisId, key) {
    const r = await this.analysis(analysisId);
    return r.test_cases.find((t) => t.requirement_keys.map((k) => k.toUpperCase()).includes(key.toUpperCase()))?.id ?? null;
  },
  async checkRequirement(analysisId, testCaseId, issue) {
    const r = await this.analysis(analysisId);
    const tc = r.test_cases.find((t) => t.id === testCaseId);
    if (!tc) throw new Error("Pick a test case to compare.");
    const pristine = r.id === SAMPLE.id && JSON.stringify(issue.steps) === JSON.stringify((sampleIssue as Issue).steps) &&
      tc.requirement_keys.includes("CLM-1482");
    if (pristine) return sampleCheck as unknown as CheckResult;
    const out = await callEngine<Omit<CheckResult, "id" | "test_case">>("check", {
      steps: issue.steps, tosca_steps: tc.steps, acceptance: issue.acceptance_criteria, key: issue.key, test_case: tc.breadcrumb,
    });
    return { ...out, id: `c-${uid()}`, test_case: tc.breadcrumb };
  },
  async postResult() {
    throw new Error("Posting to JIRA or Rally needs the server. Copy the result text instead.");
  },
};
