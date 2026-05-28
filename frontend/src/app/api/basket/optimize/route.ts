/**
 * Route handler instead of a rewrite so that long-running LLM requests
 * (smart search) are not cut off by the Next.js dev-server proxy timeout.
 */
const BACKEND = "http://localhost:8000";

export async function POST(request: Request) {
  const body = await request.text();
  const upstream = await fetch(`${BACKEND}/api/basket/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
