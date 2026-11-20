<script setup>
import { session, setSession } from './api.js'
</script>

<template>
  <header v-if="session.token" class="header">
    <strong>Mini AI Platform</strong>
    <nav aria-label="主导航">
      <router-link to="/chat">AI 对话</router-link>
      <router-link to="/knowledge">知识库</router-link>
      <router-link to="/tasks">任务中心</router-link>
      <router-link v-if="session.user?.role === 'admin'" to="/admin">系统管理</router-link>
    </nav>
    <div class="toolbar">
      <span>{{ session.user?.username }}</span>
      <el-button size="small" @click="setSession(null)">退出</el-button>
    </div>
  </header>
  <main class="main"><router-view /></main>
</template>
