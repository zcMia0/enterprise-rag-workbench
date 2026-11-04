import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: 'RAG 总览面板' } },
  { path: '/upload', name: 'upload', component: () => import('@/views/Upload.vue'), meta: { title: '上传入库' } },
  { path: '/documents', name: 'documents', component: () => import('@/views/Documents.vue'), meta: { title: '文档管理' } },
  { path: '/chunks', name: 'chunks', component: () => import('@/views/Chunks.vue'), meta: { title: 'Chunk 管理' } },
  { path: '/retrieval', name: 'retrieval', component: () => import('@/views/RetrievalDebug.vue'), meta: { title: '检索调试' } },
  { path: '/agent', name: 'agent', component: () => import('@/views/AgentChat.vue'), meta: { title: 'Agent 对话' } },
  { path: '/preferences', name: 'preferences', component: () => import('@/views/Preferences.vue'), meta: { title: '偏好管理' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
