import { createContext, useContext } from "react";
import type { Backend } from "./api/backend";

export type Page = "new" | "report" | "requirement" | "history" | "rules" | "settings";

export interface AppCtx {
  backend: Backend;
  go: (page: Page, reportId?: string) => void;
  toast: (msg: string) => void;
  /** Bumped whenever an analysis is created or deleted, so lists refresh. */
  version: number;
  bump: () => void;
  lastReportId: string | null;
}

export const Ctx = createContext<AppCtx | null>(null);

export function useApp(): AppCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp outside provider");
  return ctx;
}

export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export const fmtDateTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
