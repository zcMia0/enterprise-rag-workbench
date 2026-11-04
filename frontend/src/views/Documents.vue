<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { documentsApi, type DocumentItem } from '@/api'

const docs = ref<DocumentItem[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    docs.value = await documentsApi.list(1, 100)
  } finally {
    loading.value = false
  }
}
async function remove(id: number) {
  if (!confirm('确认物理删除该文档及其全部 chunk 与向量？')) return
  await documentsApi.remove(id)
  await load()
}
async function rebuild(id: number) {
  await documentsApi.rebuild(id)
  alert('索引已重建')
  await load()
}
onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2>文档管理</h2>
      <button class="btn" :disabled="loading" @click="load">刷新</button>
    </div>

    <div class="card">
      <table>
        <thead>
          <tr><th>ID</th><th>文件名</th><th>类型</th><th>解析链路</th><th>块数</th><th>表格/图片</th><th>状态</th><th>创建时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in docs" :key="d.id">
            <td>{{ d.id }}</td>
            <td>{{ d.filename }}</td>
            <td>{{ d.file_type }}</td>
            <td><span class="tag" :class="d.parse_path === 'ocr' ? 'orange' : 'green'">{{ d.parse_path }}</span></td>
            <td>{{ d.chunk_count }}</td>
            <td>{{ d.table_count }} / {{ d.image_count }}</td>
            <td><span class="tag green">{{ d.status }}</span></td>
            <td class="muted">{{ d.created_at?.slice(0, 19) }}</td>
            <td class="row wrap">
              <button class="btn" @click="rebuild(d.id)">重建索引</button>
              <button class="btn danger" @click="remove(d.id)">删除</button>
            </td>
          </tr>
          <tr v-if="!docs.length"><td colspan="9" class="empty">暂无文档，请先到「上传入库」上传</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
