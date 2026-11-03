<script setup lang="ts">
import { onMounted, ref, nextTick } from 'vue'
import { agentApi, streamChat, type Source, type Thread } from '@/api'

const threads = ref<Thread[]>([])
const threadId = ref<string | null>(null)
const messages = ref<{ role: 'user' | 'assistant'; content: string }[]>([])
const sources = ref<Source[]>([])
const query = ref('')
const streaming = ref(false)
const box = ref<HTMLElement | null>(null)

async function loadThreads() {
  threads.value = await agentApi.threads()
}
function newThread() {
  threadId.value = null
  messages.value = []
  sources.value = []
}
function switchThread(t: Thread) {
  alert('切换历史会话: ' + t.thread_id + '\n' + (t.last_question || ''))
}
async function send() {
  if (!query.value.trim() || streaming.value) return
  if (!threadId.value) newThread()
  const q = query.value
  query.value = ''
  messages.value.push({ role: 'user', content: q })
  messages.value.push({ role: 'assistant', content: '' })
  sources.value = []
  streaming.value = true
  await nextTick()
  scroll()
  await streamChat(
    { thread_id: threadId.value!, query: q },
    {
      onToken: (t: string) => {
        const last = messages.value[messages.value.length - 1]
        last.content += t
        scroll()
      },
      onSources: (s: Source[]) => { sources.value = s },
      onDone: () => { streaming.value = false; loadThreads() },
      onError: (e: string) => {
        const last = messages.value[messages.value.length - 1]
        last.content += `\n[错误] ${e}`
        streaming.value = false
      },
      onMeta: (m: { thread_id: string }) => { if (!threadId.value) threadId.value = m.thread_id },
    },
  )
}
function scroll() {
  nextTick(() => { if (box.value) box.value.scrollTop = box.value.scrollHeight })
}
onMounted(loadThreads)
</script>

<template>
  <div>
    <div class="page-head"><h2>Agent 对话</h2>
      <button class="btn primary" @click="newThread">+ 新会话</button>
    </div>

    <div class="grid cols-2">
      <!-- 会话列表 -->
      <div class="card">
        <div class="label" style="font-weight: 600; margin-bottom: 10px">会话历史</div>
        <div v-if="!threads.length" class="empty">暂无历史会话</div>
        <div
          v-for="t in threads" :key="t.thread_id"
          class="source-card" style="cursor: pointer"
          @click="switchThread(t)"
        >
          <div>{{ t.last_question || '(空)' }}</div>
          <div class="meta"><span>{{ t.thread_id.slice(0, 12) }}</span><span>{{ t.updated_at?.slice(0, 19) }}</span></div>
        </div>
      </div>

      <!-- 对话 + 来源 -->
      <div>
        <div class="card">
          <div class="chat-box" ref="box">
            <div v-if="!messages.length" class="empty">开始提问吧（例如：employee_id 字段含义是什么？）</div>
            <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">{{ m.content }}</div>
          </div>
          <div class="row" style="margin-top: 12px">
            <input class="input" v-model="query" placeholder="输入问题，回车发送" @keyup.enter="send" :disabled="streaming" />
            <button class="btn primary" :disabled="streaming" @click="send">{{ streaming ? '生成中…' : '发送' }}</button>
          </div>
        </div>

        <div class="card" style="margin-top: 16px">
          <div class="label" style="font-weight: 600; margin-bottom: 10px">来源溯源</div>
          <div v-if="!sources.length" class="empty">回答后将展示引用来源（chunk / 文件名 / 页码 / 分数）</div>
          <div v-for="s in sources" :key="s.chunk_id" class="source-card">
            <div class="meta">
              <span>chunk #{{ s.chunk_id }}</span>
              <span>{{ s.filename }} · p{{ s.page }}</span>
            </div>
            <div class="meta">
              <span class="tag gray">向量 {{ s.vector_score }}</span>
              <span class="tag gray">BM25 {{ s.bm25_score }}</span>
              <span class="tag orange">融合 {{ s.fused_score }}</span>
            </div>
            <div style="margin-top: 6px" class="muted">{{ s.content.slice(0, 160) }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
