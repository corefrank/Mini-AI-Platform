<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'

const route = useRoute()
const jobs = ref([]), models = ref([]), model = ref(null), prompt = ref('')
const selected = ref(route.query.id || ''), error = ref(''), busy = ref(false)
const current = computed(() => jobs.value.find(row => row.id === selected.value))
let timer
let closed = false

async function refresh() {
  const rows = await api('/tasks')
  if (selected.value && !rows.some(row => row.id === selected.value)) {
    try { rows.unshift(await api(`/tasks/${selected.value}`)) } catch { selected.value = '' }
  }
  jobs.value = rows
}
async function poll() {
  try { await refresh() }
  catch (e) { error.value = e.message }
  finally { if (!closed) timer = setTimeout(poll, 2500) }
}
async function submit() {
  busy.value = true
  error.value = ''
  try {
    const job = await api('/agent/tasks', { method: 'POST', body: { model_id: model.value, prompt: prompt.value } })
    selected.value = job.id
    prompt.value = ''
    await refresh()
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
onMounted(async () => {
  poll()
  try {
    models.value = await api('/models')
    model.value = models.value[0]?.id
  } catch (e) { error.value = e.message }
})
onUnmounted(() => { closed = true; clearTimeout(timer) })
</script>

<template>
  <h1>任务中心</h1>
  <el-alert v-if="error" :title="error" type="error" @close="error = ''" />
  <div class="stack">
    <el-card shadow="never">
      <h2>新建文档分析任务</h2>
      <el-form class="stack" @submit.prevent="submit">
        <el-select v-model="model" aria-label="分析模型" style="width: 210px">
          <el-option v-for="item in models" :key="item.id" :label="item.label" :value="item.id" />
        </el-select>
        <el-input v-model="prompt" aria-label="分析目标" type="textarea" :rows="3" maxlength="4000" placeholder="例如比较 FastAPI BackgroundTasks 与 Celery，并列出依据。" />
        <div><el-button native-type="submit" type="primary" :disabled="!model || !prompt.trim()" :loading="busy">提交 Agent 任务</el-button></div>
      </el-form>
    </el-card>
    <el-card shadow="never">
      <h2>我的任务</h2>
      <el-table :data="jobs" empty-text="暂无任务">
        <el-table-column prop="task_type" label="类型" width="90" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="attempts" label="尝试次数" width="100" />
        <el-table-column prop="id" label="任务 ID" min-width="270" />
        <el-table-column label="操作" width="125">
          <template #default="{ row }"><el-button size="small" @click="selected = row.id">查看结果</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-card v-if="current" shadow="never">
      <h2>任务详情 · {{ current.status }}</h2>
      <p class="wrap muted">请求 ID {{ current.request_id }}</p>
      <el-alert v-if="current.error" :title="current.error" type="warning" :closable="false" />
      <p v-if="current.result?.chunks">索引文档 {{ current.result.document_id }}，共 {{ current.result.chunks }} 个片段。</p>
      <template v-if="current.result?.report">
        <h2>分析报告（Markdown）</h2>
        <p class="wrap">{{ current.result.report }}</p>
        <details v-for="(item, i) in current.result.citations" :key="i">
          <summary>[D{{ item.document_id }}] {{ item.title }}</summary>
          <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener noreferrer">官方来源</a>
          <p class="wrap">{{ item.excerpt }}</p>
        </details>
        <h2>工具轨迹</h2>
        <el-table :data="current.result.trace">
          <el-table-column prop="step" label="轮次" width="90" />
          <el-table-column prop="tool" label="工具" min-width="210" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="evidence_count" label="证据数" width="100" />
        </el-table>
      </template>
    </el-card>
  </div>
</template>
