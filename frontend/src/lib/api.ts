// Thin wrapper around fetch for the FastAPI backend.
// Empty base => same-origin: /api and /auth are proxied to the backend by
// next.config.ts rewrites, so cookies stay first-party. `credentials: "include"`
// keeps working if you instead point NEXT_PUBLIC_API_URL straight at the backend.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export async function api(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
}

export async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* non-JSON body */
  }
  return `${fallback} (${res.status})`;
}
