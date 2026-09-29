import type {
  AnalysisSummary, Catalog, CheckResult, Issue, Report, RuleSet, Settings,
} from "./types";

/** Everything the screens need. Implemented by the HTTP client and by the in-browser demo. */
export interface Backend {
  mode: "server" | "demo";
  catalog(): Promise<Catalog>;
  ruleSets(): Promise<RuleSet[]>;
  saveRuleSet(rs: RuleSet): Promise<RuleSet>;
  deleteRuleSet(id: string): Promise<void>;
  settings(): Promise<Settings>;
  saveSettings(s: Partial<Settings>): Promise<Settings>;
  analyze(input: { file: File; results?: File | null; ruleSetId: string; categories: string[] }, onStage?: (s: string) => void): Promise<Report>;
  attachResults(id: string, results: File): Promise<Report>;
  analyses(): Promise<AnalysisSummary[]>;
  analysis(id: string): Promise<Report>;
  deleteAnalysis(id: string): Promise<void>;
  exportFile(report: Report, fmt: "xlsx" | "pdf"): Promise<{ filename: string; data: Blob }>;
  fetchIssue(source: "jira" | "rally", key: string): Promise<Issue>;
  matchTestCase(analysisId: string, key: string): Promise<string | null>;
  checkRequirement(analysisId: string, testCaseId: string, issue: Issue): Promise<CheckResult>;
  postResult(checkId: string): Promise<{ posted: boolean; issue: string }>;
}

export class ApiError extends Error {}

// ---------------------------------------------------------------- HTTP client

const API = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const TOKEN = import.meta.env.VITE_API_TOKEN as string | undefined;

async function http<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (TOKEN) headers.set("Authorization", `Bearer ${TOKEN}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("The server can't be reached. Check that the API is running.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch { /* keep generic */ }
    throw new ApiError(detail);
  }
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("json") ? res.json() : res.blob()) as Promise<T>;
}

export const serverBackend: Backend = {
  mode: "server",
  catalog: () => http("/api/rules"),
  ruleSets: () => http("/api/rule-sets"),
  saveRuleSet: (rs) =>
    rs.id && !rs.id.startsWith("new-")
      ? http(`/api/rule-sets/${rs.id}`, { method: "PUT", body: JSON.stringify(rs) })
      : http("/api/rule-sets", { method: "POST", body: JSON.stringify(rs) }),
  deleteRuleSet: (id) => http(`/api/rule-sets/${id}`, { method: "DELETE" }),
  settings: () => http("/api/settings"),
  saveSettings: (s) => http("/api/settings", { method: "PUT", body: JSON.stringify(s) }),
  analyze: ({ file, results, ruleSetId, categories }, onStage) => {
    const fd = new FormData();
    fd.append("file", file);
    if (results) fd.append("results", results);
    fd.append("rule_set_id", ruleSetId);
    fd.append("categories", categories.join(","));
    onStage?.("Checking rules");
    return http("/api/analyses", { method: "POST", body: fd });
  },
  attachResults: (id, results) => {
    const fd = new FormData();
    fd.append("results", results);
    return http(`/api/analyses/${id}/results`, { method: "POST", body: fd });
  },
  analyses: () => http("/api/analyses"),
  analysis: (id) => http(`/api/analyses/${id}`),
  deleteAnalysis: (id) => http(`/api/analyses/${id}`, { method: "DELETE" }),
  exportFile: async (report, fmt) => ({
    filename: `${report.file_name.replace(/\.[^.]+$/, "")}_analysis.${fmt}`,
    data: await http<Blob>(`/api/analyses/${report.id}/export.${fmt}`),
  }),
  fetchIssue: (source, key) => http("/api/requirements/fetch", { method: "POST", body: JSON.stringify({ source, key }) }),
  matchTestCase: async (analysisId, key) =>
    (await http<{ test_case_id: string | null }>(`/api/analyses/${analysisId}/match?key=${encodeURIComponent(key)}`)).test_case_id,
  checkRequirement: (analysis_id, test_case_id, issue) =>
    http("/api/requirements/check", { method: "POST", body: JSON.stringify({ analysis_id, test_case_id, issue }) }),
  postResult: (check_id) => http("/api/requirements/post", { method: "POST", body: JSON.stringify({ check_id }) }),
};

/** Use the API when it answers; otherwise run the engine in the browser. */
export async function pickBackend(): Promise<Backend> {
  if (!__DEMO_BUILD__) {
    try {
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), 2500);
      const res = await fetch(`${API}/api/health`, { signal: ctl.signal });
      clearTimeout(t);
      if (res.ok && (res.headers.get("content-type") ?? "").includes("json")) return serverBackend;
    } catch { /* fall through to demo */ }
  }
  const { demoBackend } = await import("./demo");
  return demoBackend;
}
