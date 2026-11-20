<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { api, chatEvents } from '../api.js'

const conversations = ref([]), messages = ref([]), models = ref([])
const active = ref(null), model = ref(null), mode = ref('chat'), prompt = ref('')
const error = ref(''), busy = ref(false), partial = ref(''), viewport = ref(null)
let requestController

function showError(exception) { error.value = exception.message }
async function load() {
  conversations.value = await api('/conversations')
  const list = await api('/models')
  models.value = list
  if (!model.value) model.value = list[0]?.id
}
async function selectConversation(id) {
  const data = await api(`/conversations/${id}`)
  active.value = id
  messages.value = data.messages
  partial.value = ''
  scrollToEnd()
}
async function createConversation() {
  const title = prompt.value.trim().slice(0, 40) || '新会话'
  const item = await api('/conversations', { method: 'POST', body: { title } })
  conversations.value.unshift(item)
  await selectConversation(item.id)
}
async function renameConversation() {
  const item = conversations.value.find(row => row.id === active.value)
  let value
  try {
    ({ value } = await ElMessageBox.prompt('输入会话标题', '重命名', {
      inputValue: item.title, inputValidator: text => !!text?.trim() && text.trim().length <= 120,
    }))
  } catch { return }
  const changed = await api(`/conversations/${item.id}`, { method: 'PATCH', body: { title: value } })
  conversations.value = conversations.value.map(row => row.id === item.id ? changed : row)
}
async function removeConversation() {
  try { await ElMessageBox.confirm('删除会话及其中的消息？', '删除会话') }
  catch { return }
  await api(`/conversations/${active.value}`, { method: 'DELETE' })
  conversations.value = conversations.value.filter(row => row.id !== active.value)
  active.value = null
  messages.value = []
  partial.value = ''
  if (conversations.value.length) await selectConversation(conversations.value[0].id)
}
async function scrollToEnd() {
  await nextTick()
  if (viewport.value) viewport.value.scrollTop = viewport.value.scrollHeight
}
async function send() {
  if (busy.value || !prompt.value.trim() || !model.value) return
  busy.value = true
  error.value = ''
  partial.value = ''
  requestController = new AbortController()
  const { signal } = requestController
  const question = prompt.value.trim()
  try {
    if (!active.value) await createConversation()
    await chatEvents(active.value, { model_id: model.value, mode: mode.value, message: question },
      signal, (event, payload) => {
        if (event === 'delta') partial.value += payload.text
        if (event === 'done') {
          messages.value.push({ role: 'user', content: question },
            { role: 'assistant', content: partial.value, citations: payload.citations })
          partial.value = ''
          prompt.value = ''
        }
        scrollToEnd()
      })
  } catch (exception) {
    error.value = signal.aborted ? '已停止接收，可重新打开会话确认历史记录' : exception.message
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  try {
    await load()
    if (conversations.value.length) await selectConversation(conversations.value[0].id)
  } catch (e) { showError(e) }
})
onUnmounted(() => requestController?.abort())
</script>

<template>
  <h1>AI 对话</h1>
  <el-alert v-if="error" :title="error" type="error" @close="error = ''" />
  <div class="chat-grid">
    <el-card shadow="never">
      <div class="toolbar"><h2>历史会话</h2><el-button :disabled="busy" @click="createConversation().catch(showError)">新建</el-button></div>
      <div class="thread-list">
        <button v-for="row in conversations" :key="row.id" :disabled="busy"
                :class="{ selected: active === row.id }" @click="selectConversation(row.id).catch(showError)">{{ row.title }}</button>
      </div>
    </el-card>
    <el-card shadow="never">
      <div class="toolbar">
        <el-select v-model="model" aria-label="模型" :disabled="busy" style="width: 195px">
          <el-option v-for="item in models" :key="item.id" :label="item.label" :value="item.id" />
        </el-select>
        <el-select v-model="mode" aria-label="模式" :disabled="busy" style="width: 140px">
          <el-option label="普通对话" value="chat" /><el-option label="知识库问答" value="rag" />
        </el-select>
        <el-button v-if="active" :disabled="busy" @click="renameConversation().catch(showError)">重命名</el-button>
        <el-button v-if="active" :disabled="busy" @click="removeConversation().catch(showError)">删除</el-button>
      </div>
      <div ref="viewport" class="messages">
        <p v-if="!messages.length && !partial" class="muted">输入一个技术问题开始对话。</p>
        <article v-for="(message, index) in messages" :key="index" class="message" :class="message.role">
          <strong>{{ message.role === 'user' ? '你' : '助手' }}</strong>
          <p class="wrap">{{ message.content }}</p>
          <details v-if="message.citations?.length">
            <summary>来源与证据</summary>
            <div v-for="(item, i) in message.citations" :key="i">
              <p>[{{ i + 1 }}] {{ item.title }} · 片段 {{ item.chunk }}</p>
              <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener noreferrer">官方来源</a>
              <p class="wrap">{{ item.excerpt }}</p>
            </div>
          </details>
        </article>
        <article v-if="partial" class="message"><strong>{{ busy ? '生成中' : '未保存的输出' }}</strong><p class="wrap">{{ partial }}</p></article>
      </div>
      <el-form @submit.prevent="send">
        <el-form-item><el-input v-model="prompt" aria-label="技术问题" type="textarea" :rows="3" maxlength="4000" :disabled="busy" placeholder="输入问题" /></el-form-item>
        <el-button type="primary" native-type="submit" :disabled="!prompt.trim() || !model || busy">发送</el-button>
        <el-button v-if="busy" @click="requestController?.abort()">停止</el-button>
      </el-form>
    </el-card>
  </div>
</template>
