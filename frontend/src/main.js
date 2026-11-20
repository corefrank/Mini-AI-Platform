import { createApp, watch } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
import Login from './pages/Login.vue'
import Chat from './pages/Chat.vue'
import Knowledge from './pages/Knowledge.vue'
import Tasks from './pages/Tasks.vue'
import Admin from './pages/Admin.vue'
import { session } from './api.js'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/login', component: Login },
    { path: '/chat', component: Chat },
    { path: '/knowledge', component: Knowledge },
    { path: '/tasks', component: Tasks },
    { path: '/admin', component: Admin, meta: { admin: true } },
    { path: '/:pathMatch(.*)*', redirect: '/chat' },
  ],
})
router.beforeEach(to => {
  if (!session.token && to.path !== '/login') return '/login'
  if (session.token && to.path === '/login') return '/chat'
  if (to.meta.admin && session.user?.role !== 'admin') return '/chat'
})
watch(() => session.token, token => {
  if (!token) router.replace('/login')
})

createApp(App).use(router).use(ElementPlus).mount('#app')
