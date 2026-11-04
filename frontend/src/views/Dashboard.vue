<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { documentsApi, overviewApi, type DocumentItem, type Overview } from '@/api'

const data = ref<Overview | null>(null)
const docs = ref<DocumentItem[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const [ov, list] = await Promise.all([overviewApi.get(), documentsApi.list(1, 50)])
    data.value = ov
    docs.value = list
  } finally {
    loading.value = false
  }
}
onMounted(load)

/** KPI 指标(不含图标字符: emoji 在无对应字体的环境会渲染成方块) */
const cards = [
  { key: 'documents', label: '已入库文档数', hint: 'Document 层' },
  { key: 'chunks', label: '文档切分总量', hint: 'Chunk 层' },
  { key: 'agent_sessions', label: 'Agent 会话数', hint: '对话线程' },
] as const

/** 最近入库: 按创建时间倒序取前 8 条 */
const recent = computed(() =>
  [...docs.value]
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
    .slice(0, 8),
)

/** 解析链路分布: 直观体现"双链路 + 启发式路由"真实生效 */
const routeStats = computed(() => {
  const native = docs.value.filter((d) => d.parse_path === 'native').length
  const ocr = docs.value.filter((d) => d.parse_path === 'ocr').length
  const withTable = docs.value.filter((d) => d.table_count > 0).length
  return { native, ocr, withTable }
})
</script>

<template>
  <div>
    <div class="page-head">
      <h2>RAG 整体面板</h2>
      <button class="btn" :disabled="loading" @click="load">刷新</button>
    </div>

    <div v-if="data" class="grid cols-4">
      <div v-for="c in cards" :key="c.key" class="card stat">
        <div class="label">{{ c.label }}</div>
        <div class="value">{{ data[c.key] }}</div>
        <div class="sub">{{ c.hint }}</div>
      </div>
      <div class="card stat">
        <div class="label">后台服务状态</div>
        <div class="value" style="font-size: 15px; font-weight: 600; margin-top: 10px">
          <div>
            <span
              class="badge-dot"
              :class="data.services.postgres.includes('online') ? 'dot-online' : (data.services.postgres.includes('local') ? 'dot-mock' : 'dot-offline')"
            />
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

    <div class="grid cols-2" style="margin-top: 16px">
      <div class="card">
        <div class="label" style="font-weight: 600; margin-bottom: 10px">解析链路分布</div>
        <div v-if="!docs.length" class="empty">暂无文档</div>
        <template v-else>
          <div class="row" style="gap: 10px; margin-bottom: 8px">
            <span style="width: 92px" class="muted">原生解析</span>
            <span class="score-bar" style="flex: 1">
              <span :style="{ width: (routeStats.native / docs.length) * 100 + '%' }" />
            </span>
            <span style="width: 56px; text-align: right">{{ routeStats.native }} 篇</span>
          </div>
          <div class="row" style="gap: 10px; margin-bottom: 8px">
            <span style="width: 92px" class="muted">OCR 识别</span>
            <span class="score-bar" style="flex: 1; background: #eef1f5">
              <span :style="{ width: (routeStats.ocr / docs.length) * 100 + '%', background: '#1eb980' }" />
            </span>
            <span style="width: 56px; text-align: right">{{ routeStats.ocr }} 篇</span>
          </div>
          <div class="row" style="gap: 10px">
            <span style="width: 92px" class="muted">含表格</span>
            <span class="score-bar" style="flex: 1; background: #eef1f5">
              <span :style="{ width: (routeStats.withTable / docs.length) * 100 + '%', background: '#f5a623' }" />
            </span>
            <span style="width: 56px; text-align: right">{{ routeStats.withTable }} 篇</span>
          </div>
          <p class="muted" style="margin-top: 12px; font-size: 12px">
            路由依据「是否存在文本层」: 图像必走 OCR; PDF 依据可提取字符数判定扫描件; Office / Markdown 天然带文本层走原生。
          </p>
        </template>
      </div>

      <div class="card">
        <div class="label" style="font-weight: 600; margin-bottom: 10px">最近入库</div>
        <div v-if="!recent.length" class="empty">暂无文档, 去「上传入库」试试</div>
        <table v-else>
          <thead>
            <tr><th>文件名</th><th>类型</th><th>路由</th><th>表格</th><th>Chunk</th></tr>
          </thead>
          <tbody>
            <tr v-for="d in recent" :key="d.id">
              <td class="ellipsis" :title="d.filename">{{ d.filename }}</td>
              <td>{{ d.file_type }}</td>
              <td>
                <span class="tag" :class="d.parse_path === 'ocr' ? 'orange' : 'gray'">
                  {{ d.parse_path }}
                </span>
              </td>
              <td>{{ d.table_count }}</td>
              <td>{{ d.chunk_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
