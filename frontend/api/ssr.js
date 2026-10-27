// Vercel Node.js serverless function — adapts TanStack Start's Web Fetch API handler

let serverModule;

async function getServer() {
  if (!serverModule) {
    const mod = await import('../dist/server/server.js');
    serverModule = mod.default;
  }
  return serverModule;
}

export default async function handler(req, res) {
  try {
    const server = await getServer();

    const protocol = req.headers['x-forwarded-proto'] ?? 'https';
    const host = req.headers['x-forwarded-host'] ?? req.headers.host ?? 'localhost';
    const url = `${protocol}://${host}${req.url ?? '/'}`;

    const headers = new Headers();
    for (const [key, value] of Object.entries(req.headers)) {
      if (value === undefined) continue;
      if (Array.isArray(value)) {
        value.forEach((v) => headers.append(key, v));
      } else {
        headers.set(key, value);
      }
    }

    const request = new Request(url, {
      method: req.method ?? 'GET',
      headers,
    });

    const response = await server.fetch(request, process.env, {});

    res.status(response.status);
    for (const [key, value] of response.headers.entries()) {
      if (key !== 'transfer-encoding') res.setHeader(key, value);
    }

    res.end(Buffer.from(await response.arrayBuffer()));
  } catch (err) {
    console.error('SSR error:', err);
    res.status(500).send('Internal Server Error');
  }
}
