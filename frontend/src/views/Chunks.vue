<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { chunksApi, documentsApi, type ChunkItem, type DocumentItem } from '@/api'

const state = reactive({ page: 1, size: 20, document_id: undefined as number | undefined })
const data = ref<{ total: number; items: ChunkItem[] }>({ total: 0, items: [] })
const docs = ref<DocumentItem[]>([])
const loading = ref(false)

const editing = ref<ChunkItem | null>(null)
const editText = ref('')

async function load() {
  loading.value = true
  try {
    data.value = await chunksApi.list(state.page, state.size, state.document_id)
  } finally {
    loading.value = false
  }
}
async function loadDocs() {
  docs.value = await documentsApi.list(1, 200)
}
function openEdit(c: ChunkItem) {
  editing.value = c
  editText.value = c.content
}
async function saveEdit() {
  if (!editing.value) return
  await chunksApi.update(editing.value.chunk_id, editText.value)
  editing.value = null
  await load()
}
async function remove(id: number) {
  if (!confirm('确认删除该 chunk（软删除，同步移出向量库）？')) return
  await chunksApi.remove(id)
  await load()
}
function changePage(p: number) {
  state.page = p
  load()
}
onMounted(() => { loadDocs(); load() })
</script>

<template>
  <div>
    <div class="page-head">
      <h2>Chunk 管理</h2>
      <div class="row wrap">
        <select class="input" style="max-width: 240px" v-model.number="state.document_id" @change="(state.page = 1, load())">
          <option :value="undefined">全部文档</option>
          <option v-for="d in docs" :key="d.id" :value="d.id">{{ d.filename }}</option>
        </select>
        <button class="btn" :disabled="loading" @click="load">刷新</button>
      </div>
    </div>

    <div class="card">
      <div class="muted" style="margin-bottom: 10px">共 {{ data.total }} 个 chunk（保护式切分的表格/图片块标记 PROTECTED）</div>
      <table>
        <thead>
          <tr><th>ID</th><th>文档</th><th>#</th><th>页</th><th>类型</th><th>Token</th><th>内容预览</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in data.items" :key="c.chunk_id">
            <td>{{ c.chunk_id }}</td>
            <td class="muted">{{ c.document_id }}</td>
            <td>{{ c.chunk_index }}</td>
            <td>{{ c.page }}</td>
            <td>
              <span v-if="c.protected" class="tag orange">PROTECTED</span>
              <span v-if="c.has_table" class="tag">表格</span>
              <span v-if="c.has_image" class="tag">图片</span>
              <span v-if="!c.protected && !c.has_table && !c.has_image" class="tag gray">文本</span>
            </td>
            <td>{{ c.token_count }}</td>
            <td style="max-width: 360px" class="muted">{{ c.content.slice(0, 80) }}</td>
            <td class="row wrap">
              <button class="btn" @click="openEdit(c)">编辑</button>
              <button class="btn danger" @click="remove(c.chunk_id)">删除</button>
            </td>
          </tr>
          <tr v-if="!data.items.length"><td colspan="8" class="empty">暂无 chunk，请先上传文档</td></tr>
        </tbody>
      </table>
      <div class="pagination">
        <button class="btn" :disabled="state.page <= 1" @click="changePage(state.page - 1)">上一页</button>
        <span class="muted">第 {{ state.page }} 页</span>
        <button class="btn" :disabled="data.items.length < state.size" @click="changePage(state.page + 1)">下一页</button>
      </div>
    </div>

    <div v-if="editing" class="card" style="margin-top: 16px">
      <div class="label" style="font-weight: 600; margin-bottom: 10px">
        编辑 Chunk #{{ editing.chunk_id }}
      </div>
      <textarea v-model="editText" rows="8" style="font-family: monospace"></textarea>
      <div class="row" style="margin-top: 10px">
        <button class="btn primary" @click="saveEdit">保存并重新向量化</button>
        <button class="btn" @click="editing = null">取消</button>
      </div>
    </div>
  </div>
</template>
