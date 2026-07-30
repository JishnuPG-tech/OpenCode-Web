// @ts-nocheck
// OpenCode-Web Cloudflare Worker — SSE streaming optimized

export default {
  async fetch(request, env) {
    const tunnelUrl = await env.opencode_url.get("current_url");

    // Server not started yet
    if (!tunnelUrl) {
      return new Response(
        "<html><body style='background:#09090b;color:#a1a1aa;font-family:system-ui;"
        + "display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
        + "<div style='text-align:center'><h1 style='color:#f4f4f5'>OpenCode Serve</h1>"
        + "<p>Server starting up... refreshing in 15s</p>"
        + "<script>setTimeout(()=>location.reload(),15000)</script></div></body></html>",
        { status: 503, headers: { "Content-Type": "text/html" } }
      );
    }

    const url = new URL(request.url);
    const target = tunnelUrl.replace(/\/$/, "") + url.pathname + url.search;

    try {
      const proxyReq = new Request(target, {
        method: request.method,
        headers: request.headers,
        body: ["GET", "HEAD"].includes(request.method) ? null : request.body,
        // Critical: disable redirect following for SSE
        redirect: "manual",
      });

      const resp = await fetch(proxyReq);

      // Build response headers — preserve all original headers
      const respHeaders = new Headers(resp.headers);

      // Force SSE headers if this is an event-stream
      const contentType = resp.headers.get("content-type") || "";
      if (contentType.includes("text/event-stream")) {
        respHeaders.set("Content-Type", "text/event-stream");
        respHeaders.set("Cache-Control", "no-cache, no-store, no-transform");
        respHeaders.set("X-Accel-Buffering", "no");  // Disable nginx buffering
        respHeaders.delete("Content-Length");          // Streaming = no fixed length
      }

      // Always add these performance headers
      respHeaders.set("X-Tunnel-Origin", tunnelUrl);

      // Pass body as ReadableStream — enables true token-by-token streaming
      return new Response(resp.body, {
        status: resp.status,
        statusText: resp.statusText,
        headers: respHeaders,
      });

    } catch (e) {
      return new Response(
        JSON.stringify({ error: e.message, tunnel: tunnelUrl }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
  }
};
