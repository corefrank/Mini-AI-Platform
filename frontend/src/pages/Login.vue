<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, setSession } from '../api.js'

const router = useRouter()
const username = ref(''), password = ref(''), busy = ref(false), error = ref('')
async function login() {
  busy.value = true
  error.value = ''
  try {
    setSession(await api('/auth/login', { method: 'POST', body: { username: username.value, password: password.value } }))
    await router.replace('/chat')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card class="login" shadow="never">
    <h1>登录 Mini AI Platform</h1>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-form label-position="top" @submit.prevent="login">
      <el-form-item label="用户名"><el-input v-model="username" autocomplete="username" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="password" type="password" autocomplete="current-password" show-password /></el-form-item>
      <el-button native-type="submit" type="primary" :disabled="!username || !password" :loading="busy">登录</el-button>
    </el-form>
  </el-card>
</template>
