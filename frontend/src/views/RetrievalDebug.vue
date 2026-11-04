<script setup lang="ts">
import { ref } from 'vue'
import { retrievalApi, type RetrievalHit } from '@/api'

const query = ref('emp_no 字段的类型和格式要求')
const topK = ref(3)
const hits = ref<RetrievalHit[]>([])
const loading = ref(false)
const error = ref('')

async function search() {
  loading.value = true
  error.value = ''
  try {
    hits.value = await retrievalApi.debug(query.value, topK.value)
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
function pct(v: number) {
  // 分数归一化展示 (向量/BM25 量级不同, 仅作相对可视化)
  return Math.min(100, Math.round((v / (Math.max(1, ...hits.value.map(h => Math.max(h.vector_score, h.bm25_score, h.fused_score)))) ) * 100))
}
</script>

<template>
  <div>
    <div class="page-head"><h2>检索调试</h2></div>
    <div class="card">
      <div class="row wrap">
        <input class="input" v-model="query" placeholder="输入检索 query" style="max-width: 420px" />
        <select class="input" style="max-width: 100px" v-model.number="topK">
          <option :value="3">top 3</option>
          <option :value="5">top 5</option>
          <option :value="10">top 10</option>
        </select>
        <button class="btn primary" :disabled="loading" @click="search">混合检索</button>
      </div>
      <p class="muted" style="margin-top: 10px">
        混合检索 = Milvus 向量检索 + 应用层 BM25 + RRF 融合排序。下表展示每条证据的向量分 / BM25 分 / 融合分。
      </p>
      <p v-if="error" class="tag red" style="display:inline-block">{{ error }}</p>
    </div>

    <div class="card" style="margin-top: 16px">
      <div v-if="!hits.length" class="empty">尚无检索结果，输入 query 后点击「混合检索」</div>
      <div v-for="h in hits" :key="h.chunk_id" class="source-card">
        <div class="meta">
          <span>chunk #{{ h.chunk_id }}</span>
          <span>{{ h.filename }} · p{{ h.page }}</span>
          <span class="tag gray">融合 {{ h.fused_score }}</span>
        </div>
        <div style="margin-top: 8px; font-size: 12px" class="muted">
          <div class="row" style="gap: 8px">
            <span style="width: 64px">向量分</span>
            <span class="score-bar" style="flex:1"><span :style="{ width: pct(h.vector_score) + '%' }"></span></span>
            <span>{{ h.vector_score }}</span>
          </div>
          <div class="row" style="gap: 8px; margin-top: 4px">
            <span style="width: 64px">BM25分</span>
            <span class="score-bar" style="flex:1; background:#eef1f5"><span :style="{ width: pct(h.bm25_score) + '%', background:'#1eb980' }"></span></span>
            <span>{{ h.bm25_score }}</span>
          </div>
          <div class="row" style="gap: 8px; margin-top: 4px">
            <span style="width: 64px">融合分</span>
            <span class="score-bar" style="flex:1; background:#eef1f5"><span :style="{ width: pct(h.fused_score) + '%', background:'#f5a623' }"></span></span>
            <span>{{ h.fused_score }}</span>
          </div>
        </div>
        <div style="margin-top: 8px; white-space: pre-wrap">{{ h.content.slice(0, 200) }}</div>
      </div>
    </div>
  </div>
</template>
