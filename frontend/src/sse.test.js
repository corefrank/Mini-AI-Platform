import assert from 'node:assert/strict'
import test from 'node:test'
import { consumeEvents } from './sse.js'

function byteStream(text) {
  const bytes = new TextEncoder().encode(text)
  return new ReadableStream({
    start(controller) {
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte))
      controller.close()
    },
  })
}

test('decodes fragmented UTF-8, CRLF and a terminal event', async () => {
  const received = []
  const body = byteStream('event: delta\r\ndata: {"text":"你"}\r\n\r\nevent: done\ndata: {}\n\n')
  await consumeEvents(body, (name, data) => received.push([name, data]))
  assert.deepEqual(received, [['delta', { text: '你' }], ['done', {}]])
})

test('reports provider errors and premature disconnects', async () => {
  await assert.rejects(consumeEvents(byteStream('event: error\ndata: {"message":"故障"}\n\n'), () => {}), /故障/)
  await assert.rejects(consumeEvents(byteStream('event: delta\ndata: {"text":"partial"}\n\n'), () => {}), /提前断开/)
})
