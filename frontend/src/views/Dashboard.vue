<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { overviewApi, type Overview } from '@/api'

const data = ref<Overview | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await overviewApi.get()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const cards = [
  { key: 'documents', label: '已入库文档数', icon: '🗎' },
  { key: 'chunks', label: '文档切分总量', icon: '▤' },
  { key: 'agent_sessions', label: 'Agent 会话数', icon: '💬' },
] as const
</script>

<template>
  <div>
    <div class="page-head">
      <h2>RAG 整体面板</h2>
      <button class="btn" :disabled="loading" @click="load">刷新</button>
    </div>

    <div v-if="data" class="grid cols-4">
      <div v-for="c in cards" :key="c.key" class="card stat">
        <div class="label">{{ c.icon }} {{ c.label }}</div>
        <div class="value">{{ data[c.key] }}</div>
        <div class="sub">实时统计</div>
      </div>
      <div class="card stat">
        <div class="label">⚙ 后台服务状态</div>
        <div class="value" style="font-size: 15px; font-weight: 600; margin-top: 10px">
          <div>
            <span class="badge-dot" :class="data.services.postgres.includes('online') ? 'dot-online' : (data.services.postgres.includes('local') ? 'dot-mock' : 'dot-offline')" />
            postgres: {{ data.services.postgres }}
          </div>
          <div style="margin-top: 6px">
            <span class="badge-dot" :class="data.services.redis.includes('online') ? 'dot-online' : 'dot-mock'" />
            redis: {{ data.services.redis }}
          </div>
          <div style="margin-top: 6px">
            <span class="badge-dot" :class="data.services.milvus.includes('online') ? 'dot-online' : 'dot-mock'" />
            milvus: {{ data.services.milvus }}
          </div>
        </div>
        <div class="sub">
          {{ data.mock_mode ? '当前: Mock 降级模式 (未配置密钥)' : '当前: 真实服务模式' }}
        </div>
      </div>
    </div>

    <div v-else class="card empty">加载中…</div>

    <div class="card" style="margin-top: 16px">
      <div class="label" style="font-weight: 600; margin-bottom: 10px">导航速览</div>
      <div class="grid cols-2">
        <div class="muted">· 上传入库：PDF / Docx / Markdown / TXT，自动双链路解析</div>
        <div class="muted">· 文档管理：查看入库文档、物理删除、索引重建</div>
        <div class="muted">· Chunk 管理：可观测、可编辑、可删除切分块</div>
        <div class="muted">· 检索调试：向量分 / BM25 分 / 融合分可视化</div>
        <div class="muted">· Agent 对话：多轮流式问答 + 来源溯源</div>
        <div class="muted">· 偏好管理：注入 Agent 的记忆与个性化</div>
      </div>
    </div>
  </div>
</template>
