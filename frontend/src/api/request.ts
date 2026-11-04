import axios from 'axios'

// 开发态经 Vite 代理 (/api -> :8000); 生产态后端同源托管, 直接用 /api。
const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

http.interceptors.response.use(
  (resp) => resp,
  (err) => {
    const msg = err?.response?.data?.detail || err.message || '请求失败'
    console.error('[API ERROR]', msg)
    return Promise.reject(new Error(msg))
  },
)

export interface ApiResult<T> {
  code: number
  data: T
  message?: string
}

export const api = {
  get: <T>(url: string, params?: Record<string, any>) =>
    http.get<T>(url, { params }).then((r) => r.data),
  post: <T>(url: string, body?: any) => http.post<T>(url, body).then((r) => r.data),
  put: <T>(url: string, body?: any) => http.put<T>(url, body).then((r) => r.data),
  del: <T>(url: string) => http.delete<T>(url).then((r) => r.data),
  upload: <T>(url: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post<T>(url, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
}

/**
 * 解析后端 SSE 流 (POST /api/agent/chat)。
 * 后端格式: `data: {json}\n\n`, 事件含 token / sources / done / error / meta。
 */
export async function streamChat(
  body: { thread_id?: string; query: string },
  handlers: {
    onToken?: (t: string) => void
    onSources?: (s: any[]) => void
    onDone?: (d: any) => void
    onError?: (e: string) => void
    onMeta?: (m: any) => void
  },
): Promise<void> {
  const resp = await fetch('/api/agent/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok || !resp.body) {
    handlers.onError?.(`HTTP ${resp.status}`)
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data:')) continue
      const json = line.slice(5).trim()
      if (!json) continue
      try {
        const evt = JSON.parse(json)
        if (evt.type === 'token') handlers.onToken?.(evt.data)
        else if (evt.type === 'sources') handlers.onSources?.(evt.data)
        else if (evt.type === 'done') handlers.onDone?.(evt.data)
        else if (evt.type === 'meta') handlers.onMeta?.(evt.data)
        else if (evt.type === 'error') handlers.onError?.(evt.data)
      } catch {
        /* 忽略不完整帧 */
      }
    }
  }
}

export default http
