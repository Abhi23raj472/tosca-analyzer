// Shapes returned by the API (and by the in-browser demo engine, which is the same Python code).

export type Severity = "high" | "medium" | "low";

export interface Occurrence {
  test_case_id: string;
  test_case: string;
  location: string;
  detail: string;
}

export interface Finding {
  rule_id: string;
  category: string;
  severity: Severity;
  title: string;
  message: string;
  location: string;
  current: string;
  suggested: string;
  docs: { topic: string; label: string; url: string; verified?: boolean };
  occurrences: Occurrence[];
  linked_failures: string[];
}

export interface StepValue {
  name: string;
  value: string;
  action_mode: string;
}

export interface Step {
  index: number;
  name: string;
  kind: "step" | "reference";
  module: string;
  reference: string | null;
  disabled: boolean;
  folder: string;
  values: StepValue[];
}

export interface TestCaseInfo {
  id: string;
  name: string;
  breadcrumb: string;
  description: string;
  requirement_keys: string[];
  steps: Step[];
}

export interface RunResult {
  name: string;
  status: "passed" | "failed" | "not_run";
  message: string;
  duration: string;
  test_case_id?: string;
}

export interface Report {
  id: string;
  created_at: string;
  sample?: boolean;
  file_name: string;
  workspace: string;
  source_format: string;
  rule_set: { id: string; name: string; rules_run: number };
  docs_version: string;
  docs_home: string;
  docs_check?: { checked: boolean; reachable?: number; total?: number; checked_at?: string };
  summary: {
    score: number;
    projected_score: number;
    high_findings: number;
    test_cases: number;
    steps: number;
    findings: number;
    occurrences: number;
    by_severity: Record<Severity, number>;
  };
  categories: { key: string; label: string; score: number; findings: number }[];
  findings: Finding[];
  execution: null | {
    passed: number;
    failed: number;
    not_run: number;
    total: number;
    failures_traced: number;
    unmatched: number;
  };
  results: RunResult[];
  test_cases: TestCaseInfo[];
  warnings: string[];
}

export interface AnalysisSummary {
  id: string;
  file_name: string;
  score: number;
  rule_set: string;
  created_at: string;
  test_cases: number;
  findings: number;
  high_findings: number;
  failed_runs?: number | null;
}

export interface RuleMeta {
  id: string;
  category: string;
  category_label: string;
  severity: Severity;
  name: string;
  description: string;
  docs_topic: string;
  params: Record<string, string | number>;
}

export interface RuleSet {
  id: string;
  name: string;
  builtin?: boolean;
  categories: string[];
  rules: Record<string, { enabled: boolean; severity: Severity; params: Record<string, string | number> }>;
}

export interface Catalog {
  rules: RuleMeta[];
  categories: { key: string; label: string; weight: number }[];
}

export interface ExpectedStep {
  action: string;
  expected: string;
}

export interface Issue {
  source: "jira" | "rally" | "manual";
  key: string;
  summary: string;
  status: string;
  type: string;
  steps: ExpectedStep[];
  acceptance_criteria: string[];
  steps_source: string;
  linked_test?: string | null;
  url?: string;
  warnings: string[];
}

export type RowStatus = "matched" | "partial" | "mismatch" | "missing" | "extra";

export interface CheckResult {
  id: string;
  rows: {
    n: number | null;
    action: string;
    expected: string;
    built: string[];
    tosca_steps: number[];
    status: RowStatus;
    hint: string;
  }[];
  counts: Record<RowStatus, number>;
  expected_steps: number;
  design_match: number;
  criteria: { text: string; covered: boolean; steps: number[] }[];
  criteria_covered: number;
  test_case: string;
  comment: string;
}

export interface Settings {
  docs_version: string;
  docs_live_check: boolean;
  jira: {
    base_url: string;
    deployment: "cloud" | "server";
    email: string;
    api_token: string;
    test_steps_source: string;
    acceptance_field: string;
    xray_client_id: string;
    xray_client_secret: string;
    zephyr_token: string;
  };
  rally: { base_url: string; api_key: string; workspace: string };
}
