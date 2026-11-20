import { reactive } from 'vue'
import { consumeEvents } from './sse.js'

export const session = reactive({
  token: sessionStorage.getItem('token') || '',
  user: JSON.parse(sessionStorage.getItem('user') || 'null'),
})

export function setSession(data) {
  session.token = data?.access_token || ''
  session.user = data?.user || null
  if (data) {
    sessionStorage.setItem('token', session.token)
    sessionStorage.setItem('user', JSON.stringify(session.user))
  } else {
    sessionStorage.removeItem('token')
    sessionStorage.removeItem('user')
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const headers = {}
  const token = session.token
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(body)
  }
  const response = await fetch('/api' + path, { method, headers, body, signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    if (response.status === 401 && token && token === session.token) {
      setSession(null)
    }
    throw new Error(payload?.error?.message || `请求失败（HTTP ${response.status}）`)
  }
  return response
}

export async function api(path, options) {
  const response = await request(path, options)
  return response.status === 204 ? undefined : response.json()
}

export async function chatEvents(id, body, signal, onEvent) {
  const response = await request(`/conversations/${id}/stream`, { method: 'POST', body, signal })
  if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) {
    throw new Error('服务未返回 SSE 流')
  }
  await consumeEvents(response.body, onEvent)
}
