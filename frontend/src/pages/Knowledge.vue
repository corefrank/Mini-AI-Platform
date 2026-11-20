<script setup>
import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { api } from '../api.js'

const router = useRouter()
const documents = ref([]), file = ref(null), picker = ref(null), source = ref('')
const query = ref(''), method = ref('vector'), results = ref([]), searched = ref(false)
const error = ref(''), uploadBusy = ref(false), searchBusy = ref(false)
function showError(exception) { error.value = exception.message }
async function load() { documents.value = await api('/documents') }
async function upload() {
  uploadBusy.value = true
  error.value = ''
  try {
    const body = new FormData()
    body.append('file', file.value)
    if (source.value.trim()) body.append('source_url', source.value.trim())
    const job = await api('/documents', { method: 'POST', body })
    file.value = null
    picker.value.value = ''
    source.value = ''
    await router.push({ path: '/tasks', query: { id: job.task_id } })
  } catch (e) { showError(e) }
  finally { uploadBusy.value = false }
}
async function search() {
  searchBusy.value = true
  error.value = ''
  searched.value = false
  results.value = []
  try {
    results.value = await api('/search?' + new URLSearchParams({ q: query.value.trim(), method: method.value }))
    searched.value = true
  } catch (e) { showError(e) }
  finally { searchBusy.value = false }
}
async function remove(row) {
  try { await ElMessageBox.confirm(`删除「${row.title}」？`, '删除文档') }
  catch { return }
  await api(`/documents/${row.id}`, { method: 'DELETE' })
  results.value = results.value.filter(item => item.document_id !== row.id)
  await load()
}
onMounted(() => load().catch(showError))
</script>

<template>
  <h1>知识库</h1>
  <el-alert v-if="error" :title="error" type="error" @close="error = ''" />
  <div class="stack">
    <el-card shadow="never">
      <h2>上传文档</h2>
      <el-form class="toolbar" @submit.prevent="upload">
        <input ref="picker" aria-label="选择 TXT 或 Markdown" type="file" accept=".txt,.md" @change="file = $event.target.files[0]" />
        <el-input v-model="source" aria-label="来源 URL" placeholder="来源 URL（可选）" style="width: 260px" />
        <el-button type="primary" native-type="submit" :disabled="!file" :loading="uploadBusy">提交索引任务</el-button>
      </el-form>
      <p class="muted">UTF-8 TXT 或 Markdown，每篇最多 512 KiB。</p>
    </el-card>
    <el-card shadow="never">
      <div class="toolbar"><h2>我的文档</h2><el-button @click="load().catch(showError)">刷新</el-button></div>
      <el-table :data="documents" empty-text="暂无文档">
        <el-table-column prop="title" label="文档" min-width="200" />
        <el-table-column prop="category" label="类别" min-width="100" />
        <el-table-column prop="status" label="索引状态" min-width="120" />
        <el-table-column label="操作" width="105">
          <template #default="{ row }"><el-button size="small" :disabled="['PENDING','RUNNING'].includes(row.status)" @click="remove(row).catch(showError)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-card shadow="never">
      <h2>检索试验</h2>
      <el-form class="toolbar" @submit.prevent="search">
        <el-input v-model="query" aria-label="检索词" maxlength="500" placeholder="例如 Redis key expiration" style="width: 300px" />
        <el-select v-model="method" aria-label="检索方法" style="width: 135px">
          <el-option label="向量检索" value="vector" /><el-option label="BM25" value="bm25" />
        </el-select>
        <el-button native-type="submit" :disabled="query.trim().length < 2" :loading="searchBusy">检索</el-button>
      </el-form>
      <p v-if="searched && !results.length" class="muted">没有可展示的证据。</p>
      <details v-for="(item, i) in results" :key="i">
        <summary>{{ i + 1 }}. {{ item.title }} · 片段 {{ item.chunk }} · {{ item.score }}</summary>
        <p class="wrap">{{ item.excerpt }}</p>
      </details>
    </el-card>
  </div>
</template>
