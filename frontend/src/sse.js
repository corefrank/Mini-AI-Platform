// 一个网络分块可能只有半条 SSE 事件或半个汉字。
export async function consumeEvents(body, onEvent) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let pending = ''
  let finished = false
  try {
    while (!finished) {
      const { value, done } = await reader.read()
      pending += decoder.decode(value, { stream: !done })
      const events = pending.split(/\r?\n\r?\n/)
      pending = events.pop()
      for (const raw of events) {
        const lines = raw.split(/\r?\n/)
        const kind = lines.find(line => line.startsWith('event:'))?.slice(6).trim()
        const data = lines.filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trimStart()).join('\n')
        if (!kind || !data) continue
        const payload = JSON.parse(data)
        if (kind === 'error') throw new Error(payload.message)
        onEvent(kind, payload)
        if (kind === 'done') {
          finished = true
          break
        }
      }
      if (done && !finished) throw new Error('响应提前断开')
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
