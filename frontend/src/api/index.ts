import { api } from './request'

// ---------------- 类型 ----------------
export interface DocumentItem {
  id: number
  filename: string
  file_type: string
  status: string
  table_count: number
  image_count: number
  text_density: number | null
  parse_path: string
  page_count: number
  chunk_count: number
  created_at: string | null
}

export interface UploadResult {
  document_id: number
  filename: string
  parse_path: string
  chunk_count: number
  table_count: number
  image_count: number
  status: string
}

export interface ChunkItem {
  chunk_id: number
  document_id: number
  chunk_index: number
  page: number
  has_table: boolean
  has_image: boolean
  protected: boolean
  token_count: number
  content: string
  updated_at: string | null
}

export interface ChunkPage {
  total: number
  page: number
  size: number
  items: ChunkItem[]
}

export interface RetrievalHit {
  chunk_id: number
  document_id: number
  filename: string
  page: number
  content: string
  vector_score: number
  bm25_score: number
  fused_score: number
  source: string
}

export interface Overview {
  documents: number
  chunks: number
  agent_sessions: number
  services: {
    postgres: string
    redis: string
    milvus: string
    db_backend: string
  }
  mock_mode: boolean
}

export interface Source {
  chunk_id: number
  filename: string
  page: number
  vector_score: number
  bm25_score: number
  fused_score: number
  content: string
}

export interface Preference {
  key: string
  value: string
  description: string
  updated_at: string | null
}

export interface Thread {
  thread_id: string
  last_question: string | null
  updated_at: string | null
}

// ---------------- 调用 ----------------
export const overviewApi = {
  get: () => api.get<Overview>('/overview'),
}

export const uploadApi = {
  upload: (file: File) => api.upload<UploadResult>('/upload', file),
}

export const documentsApi = {
  list: (page = 1, size = 50) => api.get<DocumentItem[]>('/documents', { page, size }),
  get: (id: number) => api.get<DocumentItem>(`/documents/${id}`),
  remove: (id: number) => api.del(`/documents/${id}`),
  rebuild: (id: number) => api.post(`/documents/${id}/rebuild`),
}

export const chunksApi = {
  list: (page = 1, size = 20, document_id?: number) =>
    api.get<ChunkPage>('/chunks', { page, size, document_id }),
  get: (id: number) => api.get<ChunkItem>(`/chunks/${id}`),
  update: (id: number, content: string) =>
    api.put<ChunkItem>(`/chunks/${id}`, { content }),
  remove: (id: number) => api.del(`/chunks/${id}`),
}

export const retrievalApi = {
  debug: (query: string, top_k = 10, document_id?: number) =>
    api.post<RetrievalHit[]>('/retrieval/debug', { query, top_k, document_id }),
}

export const agentApi = {
  threads: () => api.get<Thread[]>('/agent/threads'),
  newThread: () => api.post<Thread>('/agent/threads'),
}

export const preferencesApi = {
  list: () => api.get<Preference[]>('/preferences'),
  upsert: (key: string, value: string, description = '') =>
    api.put<Preference>('/preferences', { key, value, description }),
  remove: (key: string) => api.del(`/preferences/${key}`),
}

// SSE 流式聊天封装 (来自 request.ts)
export { streamChat } from './request'
