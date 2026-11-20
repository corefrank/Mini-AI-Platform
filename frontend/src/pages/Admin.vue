<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'

const users = ref([]), models = ref([]), logs = ref([])
const choice = ref(null), config = ref(null), filter = ref(''), error = ref(''), success = ref('')
const tab = ref('users'), saving = ref(false)
function showError(exception) { error.value = exception.message }
async function selectModel(id) {
  choice.value = id
  config.value = null
  config.value = await api(`/models/${id}`)
}
async function save() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    const { model, temperature, max_tokens } = config.value
    config.value = await api(`/models/${choice.value}`, { method: 'PATCH', body: { model, temperature, max_tokens } })
    success.value = '已保存模型配置'
  } catch (e) { showError(e) }
  finally { saving.value = false }
}
async function reloadLogs() {
  error.value = ''
  const query = filter.value.trim() ? '?' + new URLSearchParams({ request_id: filter.value.trim() }) : ''
  logs.value = await api('/admin/logs' + query)
}
onMounted(async () => {
  try {
    [users.value, models.value] = await Promise.all([api('/admin/users'), api('/models')])
    if (models.value.length) await selectModel(models.value[0].id)
  } catch (e) { showError(e) }
})
</script>

<template>
  <h1>系统管理</h1>
  <el-alert v-if="error" :title="error" type="error" @close="error = ''" />
  <el-card shadow="never">
    <el-tabs v-model="tab" @tab-change="name => name === 'logs' && reloadLogs().catch(showError)">
      <el-tab-pane label="用户" name="users">
        <el-table :data="users">
          <el-table-column prop="id" label="ID" width="90" />
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="role" label="角色" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="模型配置" name="models">
        <el-select :model-value="choice" aria-label="选择模型配置" :disabled="saving" style="width: 225px" @change="id => selectModel(id).catch(showError)">
          <el-option v-for="item in models" :key="item.id" :label="item.label" :value="item.id" />
        </el-select>
        <p v-if="success" role="status">{{ success }}</p>
        <el-form v-if="config" label-position="top" style="max-width: 440px; margin-top: 16px" @submit.prevent="save">
          <el-form-item label="OpenRouter Model ID"><el-input v-model="config.model" /></el-form-item>
          <el-form-item label="Temperature"><el-input-number v-model="config.temperature" :min="0" :max="2" :step="0.1" /></el-form-item>
          <el-form-item label="Max tokens"><el-input-number v-model="config.max_tokens" :min="64" :max="8192" /></el-form-item>
          <el-button type="primary" native-type="submit" :loading="saving">保存</el-button>
        </el-form>
      </el-tab-pane>
      <el-tab-pane label="调用日志" name="logs">
        <el-form class="toolbar" @submit.prevent="reloadLogs().catch(showError)">
          <el-input v-model="filter" aria-label="请求 ID" placeholder="按请求 ID 筛选" style="width: 310px" />
          <el-button native-type="submit">查询</el-button>
        </el-form>
        <el-table :data="logs" empty-text="暂无日志">
          <el-table-column prop="request_id" label="请求 ID" min-width="255" />
          <el-table-column prop="user_id" label="用户" width="70" />
          <el-table-column prop="kind" label="类型" width="110" />
          <el-table-column prop="model" label="模型" min-width="170" />
          <el-table-column prop="requested_at" label="请求时间" min-width="205" />
          <el-table-column prop="duration_ms" label="耗时 ms" width="100" />
          <el-table-column prop="status" label="状态" width="125" />
          <el-table-column label="Tokens" width="90"><template #default="{ row }">{{ row.usage?.total_tokens ?? '—' }}</template></el-table-column>
          <el-table-column prop="error" label="错误" min-width="170" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>
