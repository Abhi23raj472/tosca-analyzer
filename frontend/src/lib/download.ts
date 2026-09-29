// Save a generated file. Inside a Claude artifact the page can't start downloads itself,
// so it asks the viewer through the `downloads` capability; everywhere else a normal link works.

type Downloads = { save(req: { filename: string; data: Blob }): Promise<{ status: string }> };
type ClaudeHost = { use(name: string): Promise<unknown> };

let downloadsNs: Promise<Downloads | null> | null = null;

function artifactDownloads(): Promise<Downloads | null> {
  const host = (window as unknown as { claude?: ClaudeHost }).claude;
  if (!host?.use) return Promise.resolve(null);
  downloadsNs ??= host.use("downloads").then((d) => (d as Downloads) ?? null).catch(() => null);
  return downloadsNs;
}

export async function saveFile(filename: string, data: Blob): Promise<string> {
  const dl = await artifactDownloads();
  if (dl) {
    try {
      await dl.save({ filename, data });
      return `Saved ${filename}`;
    } catch (err) {
      const code = (err as { code?: string }).code;
      if (code === "declined") return "Download cancelled";
      throw new Error("This view can't save files. Open the app outside the preview to export.");
    }
  }
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  return `Downloaded ${filename}`;
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
