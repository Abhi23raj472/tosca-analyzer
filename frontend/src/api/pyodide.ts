// Runs the Python analysis engine (backend/app/engine) in the browser with Pyodide.
// Loaded lazily: the demo's sample report is precomputed, so this only starts when
// someone analyzes their own file or edits a requirement check.
import type { PyodideInterface } from "pyodide";

const sources = import.meta.glob("../../../backend/app/engine/*.py", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const BRIDGE = `
import json, sys
sys.path.insert(0, "/")
from app import engine as E

def _call(name, args_json):
    a = json.loads(args_json)
    try:
        if name == "analyze":
            results = None
            if a.get("results_path"):
                results = E.parse_execution(open(a["results_path"], "rb").read(), a["results_name"])
            out = E.analyze_file(open(a["path"], "rb").read(), a["name"], a.get("rule_set"),
                                 a.get("categories") or None, a.get("docs_version", "2026.1"), results)
        elif name == "results":
            out = E.parse_execution(open(a["path"], "rb").read(), a["name"])
        elif name == "check":
            out = E.requirement_check(a["steps"], a["tosca_steps"], a.get("acceptance") or [])
            from app.engine.requirement import comment_text
            out["comment"] = comment_text(a.get("key", ""), a.get("test_case", ""), out)
        else:
            raise ValueError("unknown call " + name)
        return json.dumps({"ok": out})
    except E.ParseError as exc:
        return json.dumps({"error": str(exc)})
`;

let ready: Promise<PyodideInterface> | null = null;

export function startEngine(): Promise<PyodideInterface> {
  ready ??= (async () => {
    const { loadPyodide } = await import("pyodide");
    const indexURL = new URL("./pyodide/", document.baseURI).href;
    // The stdlib archive ships as .wasm because artifact hosting doesn't serve .zip; Pyodide only reads the bytes.
    const py = await loadPyodide({ indexURL, stdLibURL: indexURL + "python_stdlib.wasm" });
    py.FS.mkdirTree("/app/engine");
    py.FS.writeFile("/app/__init__.py", "");
    for (const [path, code] of Object.entries(sources)) {
      py.FS.writeFile(`/app/engine/${path.split("/").pop()}`, code);
    }
    py.runPython(BRIDGE);
    return py;
  })().catch((err) => {
    ready = null;
    throw err;
  });
  return ready;
}

let seq = 0;

export async function callEngine<T>(name: string, args: Record<string, unknown>, files: Record<string, File> = {}): Promise<T> {
  let py: PyodideInterface;
  try {
    py = await startEngine();
  } catch {
    throw new Error(
      "The in-browser engine couldn't start here. Run the Tosca Analyzer server to analyze your own files; the sample report still works.",
    );
  }
  const payload: Record<string, unknown> = { ...args };
  for (const [key, file] of Object.entries(files)) {
    const path = `/tmp/upload_${++seq}`;
    py.FS.writeFile(path, new Uint8Array(await file.arrayBuffer()));
    payload[key] = path;
  }
  const call = py.globals.get("_call");
  const raw = call(name, JSON.stringify(payload)) as string;
  const parsed = JSON.parse(raw);
  if (parsed.error) throw new Error(parsed.error);
  return parsed.ok as T;
}
