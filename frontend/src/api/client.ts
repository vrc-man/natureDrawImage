const BASE = ''

export async function api<T = any>(method: string, url: string, body?: any): Promise<T> {
  const opts: RequestInit = { method, headers: {} }
  if (body) {
    opts.headers = { 'Content-Type': 'application/json' }
    opts.body = JSON.stringify(body)
  }
  const r = await fetch(BASE + url, opts)
  if (!r.ok) {
    const d = await r.json().catch(() => ({}))
    throw new Error(d.detail || d.error || `HTTP ${r.status}`)
  }
  return r.json()
}

export async function apiRaw(url: string, opts?: RequestInit): Promise<Response> {
  return fetch(BASE + url, opts)
}
