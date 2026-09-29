// Turn the single-file demo build into an artifact page: the artifact host supplies
// <!doctype>, <html>, <head> and <body>, so keep only the title, links, styles, root and script.
import fs from "node:fs";

const html = fs.readFileSync("dist-demo/index.html", "utf8");
// Keep the head's own content in order (title and font links first, then the inlined
// module script and styles); only the charset/viewport meta tags come from the host skeleton.
const headStart = html.indexOf("<head>") + "<head>".length;
const headEnd = html.lastIndexOf("</head>");
const head = html.slice(headStart, headEnd).replace(/<meta [^>]*>/g, "").trim();
if (!head.startsWith("<title>") || !head.includes('<script type="module"')) throw new Error("unexpected build output");
const page = head + '\n<div id="root"></div>\n';
fs.mkdirSync("artifact", { recursive: true });
fs.writeFileSync("artifact/index.html", page);
for (const f of ["pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.wasm", "pyodide-lock.json", "pyodide.mjs"]) {
  fs.mkdirSync("artifact/pyodide", { recursive: true });
  fs.copyFileSync(`public/pyodide/${f}`, `artifact/pyodide/${f}`);
}
console.log(`artifact/index.html ${(page.length / 1024).toFixed(0)} KB`);
