<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => (route.meta.title as string) || '企业知识库 RAG 工作台')

const nav = [
  { to: '/', label: 'RAG 总览面板', icon: '▦' },
  { to: '/upload', label: '上传入库', icon: '⬆' },
  { to: '/documents', label: '文档管理', icon: '🗎' },
  { to: '/chunks', label: 'Chunk 管理', icon: '▤' },
  { to: '/retrieval', label: '检索调试', icon: '🔍' },
  { to: '/agent', label: 'Agent 对话', icon: '💬' },
  { to: '/preferences', label: '偏好管理', icon: '⚙' },
]
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        企业知识库 RAG 工作台
        <small>Enterprise RAG Workbench</small>
      </div>
      <router-link
        v-for="n in nav"
        :key="n.to"
        :to="n.to"
        class="nav-item"
        :class="{ active: route.path === n.to }"
      >
        <span>{{ n.icon }}</span><span>{{ n.label }}</span>
      </router-link>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="title">{{ title }}</div>
        <div class="muted">四层知识管理 · 混合检索 · Agent 溯源</div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>
