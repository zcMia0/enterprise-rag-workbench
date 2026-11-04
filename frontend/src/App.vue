<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => (route.meta.title as string) || '企业知识库 RAG 工作台')

/**
 * 导航项图标统一使用内联 SVG(stroke 取 currentColor)。
 * 不用 emoji / 特殊符号: 它们在缺少对应字体的环境(如无头浏览器截图、Linux 容器)
 * 会渲染成方块, 截进 README 会显得很粗糙。
 */
const nav = [
  {
    to: '/',
    label: 'RAG 总览面板',
    paths: ['M3 3h7v7H3z', 'M14 3h7v7h-7z', 'M3 14h7v7H3z', 'M14 14h7v7h-7z'],
  },
  {
    to: '/upload',
    label: '上传入库',
    paths: ['M12 16V4', 'M7 9l5-5 5 5', 'M4 20h16'],
  },
  {
    to: '/documents',
    label: '文档管理',
    paths: ['M6 3h8l4 4v14H6z', 'M14 3v5h5', 'M9 13h6', 'M9 17h6'],
  },
  {
    to: '/chunks',
    label: 'Chunk 管理',
    paths: ['M4 6h16', 'M4 12h16', 'M4 18h10'],
  },
  {
    to: '/retrieval',
    label: '检索调试',
    paths: ['M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z', 'M20 20l-4.2-4.2'],
  },
  {
    to: '/agent',
    label: 'Agent 对话',
    paths: ['M4 5h16v11H9l-5 4z', 'M8 10h8'],
  },
  {
    to: '/preferences',
    label: '偏好管理',
    paths: ['M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z', 'M12 2v3', 'M12 19v3', 'M2 12h3', 'M19 12h3', 'M4.9 4.9l2.1 2.1', 'M17 17l2.1 2.1', 'M19.1 4.9L17 7', 'M7 17l-2.1 2.1'],
  },
]
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-name">企业知识库 RAG 工作台</span>
        <small>Enterprise RAG Workbench</small>
      </div>
      <router-link
        v-for="n in nav"
        :key="n.to"
        :to="n.to"
        class="nav-item"
        :class="{ active: route.path === n.to }"
      >
        <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path v-for="(d, i) in n.paths" :key="i" :d="d" />
        </svg>
        <span>{{ n.label }}</span>
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
