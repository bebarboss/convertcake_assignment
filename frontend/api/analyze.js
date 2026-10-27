// Server-side proxy → /analyze (avoids CORS + ngrok browser warning)
export default async function handler(req, res) {
  const backendBase = (process.env.API_BASE ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
  const query = req.url.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
  const targetUrl = `${backendBase}/analyze${query}`;

  try {
    const response = await fetch(targetUrl, {
      headers: { "ngrok-skip-browser-warning": "true" },
    });
    const body = await response.arrayBuffer();
    const ct = response.headers.get("content-type");
    if (ct) res.setHeader("content-type", ct);
    res.status(response.status).end(Buffer.from(body));
  } catch (err) {
    console.error("Proxy error:", err);
    res.status(502).json({ detail: "Backend unreachable" });
  }
}
