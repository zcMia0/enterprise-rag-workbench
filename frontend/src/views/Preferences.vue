<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { preferencesApi, type Preference } from '@/api'

const prefs = ref<Preference[]>([])
const form = reactive({ key: '', value: '', description: '' })
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    prefs.value = await preferencesApi.list()
  } finally {
    loading.value = false
  }
}
async function save() {
  if (!form.key || !form.value) return
  await preferencesApi.upsert(form.key, form.value, form.description)
  form.key = ''; form.value = ''; form.description = ''
  await load()
}
async function remove(key: string) {
  await preferencesApi.remove(key)
  await load()
}
onMounted(load)
</script>

<template>
  <div>
    <div class="page-head"><h2>偏好管理</h2>
      <button class="btn" :disabled="loading" @click="load">刷新</button>
    </div>

    <div class="card">
      <div class="label" style="font-weight: 600; margin-bottom: 10px">新增 / 更新偏好</div>
      <div class="row wrap">
        <input class="input" v-model="form.key" placeholder="键 (如 tone)" style="max-width: 160px" />
        <input class="input" v-model="form.value" placeholder="值 (如 专业简洁)" style="max-width: 240px" />
        <input class="input" v-model="form.description" placeholder="说明 (可选)" style="max-width: 240px" />
        <button class="btn primary" @click="save">保存</button>
      </div>
      <p class="muted" style="margin-top: 10px">偏好会在 Agent 对话时注入系统提示，实现个性化记忆。</p>
    </div>

    <div class="card" style="margin-top: 16px">
      <table>
        <thead><tr><th>键</th><th>值</th><th>说明</th><th>更新时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="p in prefs" :key="p.key">
            <td><span class="tag">{{ p.key }}</span></td>
            <td>{{ p.value }}</td>
            <td class="muted">{{ p.description }}</td>
            <td class="muted">{{ p.updated_at?.slice(0, 19) }}</td>
            <td><button class="btn danger" @click="remove(p.key)">删除</button></td>
          </tr>
          <tr v-if="!prefs.length"><td colspan="5" class="empty">暂无偏好</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
