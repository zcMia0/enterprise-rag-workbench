<script setup lang="ts">
import { ref } from 'vue'
import { uploadApi, type UploadResult } from '@/api'

const file = ref<File | null>(null)
const uploading = ref(false)
const result = ref<UploadResult | null>(null)
const error = ref('')

function onFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  file.value = f || null
  result.value = null
  error.value = ''
}

async function submit() {
  if (!file.value) {
    error.value = '请先选择文件'
    return
  }
  uploading.value = true
  error.value = ''
  try {
    result.value = await uploadApi.upload(file.value)
  } catch (e: any) {
    error.value = e.message
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div>
    <div class="page-head"><h2>上传入库</h2></div>
    <div class="card">
      <div class="row wrap">
        <input class="input" type="file" accept=".pdf,.docx,.doc,.md,.txt" @change="onFile" style="max-width: 420px" />
        <button class="btn primary" :disabled="uploading" @click="submit">
          {{ uploading ? '解析中…' : '上传并解析' }}
        </button>
      </div>
      <p class="muted" style="margin-top: 12px">
        支持 PDF / Docx / Markdown / TXT。系统将按文件特征自动选择「原生解析」或「OCR 智能识别」
        链路，并对表格 / 图片做保护式切分。未配置密钥时以 Mock 模式运行（确定性哈希向量 + 规则化生成）。
      </p>
      <p v-if="error" class="tag red" style="display:inline-block">{{ error }}</p>
    </div>

    <div v-if="result" class="card" style="margin-top: 16px">
      <div class="label" style="font-weight: 600; margin-bottom: 10px">解析结果</div>
      <table>
        <tbody>
          <tr><th style="width:160px">文档 ID</th><td>{{ result.document_id }}</td></tr>
          <tr><th>文件名</th><td>{{ result.filename }}</td></tr>
          <tr><th>解析链路</th><td>
            <span class="tag" :class="result.parse_path === 'ocr' ? 'orange' : 'green'">
              {{ result.parse_path === 'ocr' ? 'OCR 智能识别' : '原生解析' }}
            </span>
          </td></tr>
          <tr><th>切分块数</th><td>{{ result.chunk_count }}</td></tr>
          <tr><th>表格数 / 图片数</th><td>{{ result.table_count }} / {{ result.image_count }}</td></tr>
          <tr><th>状态</th><td><span class="tag green">{{ result.status }}</span></td></tr>
        </tbody>
      </table>
      <p class="muted" style="margin-top: 10px">前往「Chunk 管理」可观测与编辑切分结果。</p>
    </div>
  </div>
</template>
