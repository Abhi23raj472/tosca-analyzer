// Copy the Pyodide runtime next to the page so the in-browser engine can load it.
import fs from "node:fs";
fs.mkdirSync("public/pyodide", { recursive: true });
for (const f of ["pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json", "pyodide.mjs"]) {
  fs.copyFileSync(`node_modules/pyodide/${f}`, `public/pyodide/${f.replace("python_stdlib.zip", "python_stdlib.wasm")}`);
}
