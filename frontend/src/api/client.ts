// All requests go through the Vite proxy: /api/* -> backend (port 8000).

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T
  let message = res.statusText
  try {
    const body = await res.json()
    const d = body.detail
    message = typeof d === 'string' ? d : JSON.stringify(d)
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(res.status, message)
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parse<T>(res)
}

export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api${path}`, { method: 'POST', body: form })
  return parse<T>(res)
}

export async function getJson<T>(path: string): Promise<T> {
  return parse<T>(await fetch(`/api${path}`))
}
