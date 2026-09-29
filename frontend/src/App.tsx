import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { pickBackend, type Backend } from "./api/backend";
import { Ctx, type Page } from "./app-context";
import { Logo, Spinner } from "./components/Icons";
import NewAnalysis from "./pages/NewAnalysis";
import ReportPage from "./pages/Report";
import RequirementCheck from "./pages/RequirementCheck";
import History from "./pages/History";
import RuleSets from "./pages/RuleSets";
import SettingsPage from "./pages/Settings";

const NAV: { page: Page; label: string }[] = [
  { page: "new", label: "New analysis" },
  { page: "requirement", label: "Requirement check" },
  { page: "history", label: "History" },
  { page: "rules", label: "Rule sets" },
  { page: "settings", label: "Settings" },
];
const HASHES: Page[] = ["new", "requirement", "history", "rules", "settings"];

function initialPage(): Page {
  const h = window.location.hash.replace("#", "") as Page;
  return HASHES.includes(h) ? h : "new";
}

export default function App() {
  const [backend, setBackend] = useState<Backend | null>(null);
  const [page, setPage] = useState<Page>(initialPage);
  const [reportId, setReportId] = useState<string | null>(null);
  const [lastReportId, setLastReportId] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const timer = useRef<number>();

  useEffect(() => {
    pickBackend().then(setBackend);
  }, []);

  const go = useCallback((p: Page, id?: string) => {
    setPage(p);
    if (id) {
      setReportId(id);
      setLastReportId(id);
    }
    if (HASHES.includes(p)) {
      try { history.replaceState(null, "", `#${p}`); } catch { /* sandboxed */ }
    }
    window.scrollTo({ top: 0 });
  }, []);

  const toast = useCallback((m: string) => {
    setToastMsg(m);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToastMsg(null), 3200);
  }, []);

  const ctx = useMemo(
    () => backend && { backend, go, toast, version, bump: () => setVersion((v) => v + 1), lastReportId },
    [backend, go, toast, version, lastReportId],
  );

  const active: Page = page === "report" ? "history" : page;

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <button className="brand" onClick={() => go("new")} aria-label="Tosca Analyzer home">
            <Logo />
            <span>Tosca Analyzer</span>
          </button>
          <nav className="nav" aria-label="Main">
            {NAV.map((n) => (
              <button key={n.page} aria-current={active === n.page ? "page" : undefined} onClick={() => go(n.page)}>
                {n.label}
              </button>
            ))}
          </nav>
          <div className="avatar" title="Signed in">AK</div>
        </div>
      </header>
      {backend?.mode === "demo" && (
        <div className="mode-banner">
          <div>Preview: the analysis engine runs in your browser and history stays on this device. JIRA and Rally need the server.</div>
        </div>
      )}
      {!ctx ? (
        <div className="loading-screen"><div className="row"><Spinner /> Connecting…</div></div>
      ) : (
        <Ctx.Provider value={ctx}>
          <main>
            {page === "new" && <NewAnalysis />}
            {page === "report" && reportId && <ReportPage id={reportId} />}
            {page === "requirement" && <RequirementCheck />}
            {page === "history" && <History />}
            {page === "rules" && <RuleSets />}
            {page === "settings" && <SettingsPage />}
          </main>
        </Ctx.Provider>
      )}
      {toastMsg && <div className="toast" role="status">{toastMsg}</div>}
    </>
  );
}
