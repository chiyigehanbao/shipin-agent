// ============================================
// 后端 API 服务层
// ============================================
// 统一封装后端 REST 接口调用与生成图片的访问地址。
// ============================================

const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

// 生成图片 URL -> 后端 /media 静态资源
export function mediaUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//.test(path)) return path
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

// 通用请求封装
async function request(path, options = {}) {
  const isForm = options.body instanceof FormData
  const headers = {
    ...(isForm ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers || {}),
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    let body = {}
    try {
      body = await res.json()
    } catch (e) {
      /* ignore */
    }
    const payload = typeof body.detail === 'object' && body.detail
      ? body.detail
      : { message: body.detail }
    const error = new Error(payload.message || `HTTP ${res.status}`)
    error.code = payload.code || ''
    error.field = payload.field || ''
    error.status = res.status
    throw error
  }
  return res.json()
}

export const assetsApi = {
  // 获取项目资产列表，type: character / scene / prop / 缺省全部
  list(projectId, type) {
    const q = type ? `?type=${type}` : ''
    return request(`/api/assets/${projectId}/assets${q}`)
  },

  // 获取单个资产（含状态）
  get(projectId, assetId) {
    return request(`/api/assets/${projectId}/${assetId}`)
  },

  // 提交资产生成（异步，返回 generating 状态资产）
  generate(projectId, payload) {
    return request(`/api/assets/${projectId}/generate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  // 从剧本同步角色/场景草稿（不自动入队生图）
  syncFromScript(projectId, payload = {}) {
    return request(`/api/assets/${projectId}/sync-from-script`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  readiness(projectId) {
    return request(`/api/assets/${projectId}/readiness`)
  },

  castCharacter(projectId, assetId) {
    return request(`/api/assets/${projectId}/characters/${assetId}/cast`, {
      method: 'POST',
      body: '{}',
    })
  },

  selectCharacter(projectId, assetId) {
    return request(`/api/assets/${projectId}/characters/${assetId}/select`, {
      method: 'POST',
      body: '{}',
    })
  },

  identityReference(projectId, assetId) {
    return request(`/api/assets/${projectId}/${assetId}/identity-reference`)
  },

  autoIdentityReference(projectId, assetId) {
    return request(`/api/assets/${projectId}/${assetId}/identity-reference/auto`, {
      method: 'POST',
      body: '{}',
    })
  },

  cropIdentityReference(projectId, assetId, crop) {
    return request(`/api/assets/${projectId}/${assetId}/identity-reference/crop`, {
      method: 'POST',
      body: JSON.stringify(crop),
    })
  },

  uploadIdentityReference(projectId, assetId, file) {
    const form = new FormData()
    form.append('file', file)
    return request(`/api/assets/${projectId}/${assetId}/identity-reference/upload`, {
      method: 'POST',
      body: form,
    })
  },

  confirmIdentityReference(projectId, assetId, candidateId) {
    return request(`/api/assets/${projectId}/${assetId}/identity-reference/confirm`, {
      method: 'POST',
      body: JSON.stringify({ candidate_id: candidateId }),
    })
  },

  generateIdentityReference(projectId, assetId, seed = null) {
    return request(`/api/assets/${projectId}/${assetId}/identity-reference/generate`, {
      method: 'POST',
      body: JSON.stringify({ seed }),
    })
  },
}

export const promptArchitectureApi = {
  compileH3(payload) {
    return request('/api/prompts/h3/compile', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  latestH3(projectId, sourceType, sourceId, durationSec = 5.17) {
    return request(
      `/api/prompts/h3/latest/${projectId}/${sourceType}/${sourceId}?duration_sec=${durationSec}`,
    )
  },
  updateH3(compiledPromptId, payload) {
    return request(`/api/prompts/h3/${compiledPromptId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
  lockH3(compiledPromptId, content, durationSec = 124 / 24) {
    return request(`/api/prompts/h3/${compiledPromptId}`, {
      method: 'PUT',
      body: JSON.stringify({ content, status: 'locked', duration_sec: durationSec }),
    })
  },
  getVisualBible(projectId) {
    return request(`/api/prompts/visual-bible/${projectId}`)
  },
  updateVisualBible(projectId, payload) {
    return request(`/api/prompts/visual-bible/${projectId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
}

export const modelsApi = {
  // 模型服务状态（sd 的 online/queue 来自后端真实探活）
  services() {
    return request('/api/models/services')
  },

  // 测试连接：后端对 sd/flux/ltx 打 ComfyUI health
  testConnection(serviceId) {
    return request(`/api/models/services/${serviceId}/test`, { method: 'POST', body: '{}' })
  },

  // 更新服务配置（sd 可持久化 api_url）
  updateConfig(serviceId, config) {
    return request(`/api/models/services/${serviceId}/config`, {
      method: 'POST',
      body: JSON.stringify(config),
    })
  },

  // 磁盘权重就绪：用于 Select 禁用未下载完的模型
  readiness() {
    return request('/api/models/readiness')
  },
}

export const promptsApi = {
  polish(payload) {
    return request('/api/prompts/polish', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  list(params = {}) {
    const q = new URLSearchParams(
      Object.fromEntries(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
      ),
    ).toString()
    return request(`/api/prompts${q ? `?${q}` : ''}`)
  },
  get(id) {
    return request(`/api/prompts/${id}`)
  },
  update(id, body) {
    return request(`/api/prompts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    })
  },
  create(body) {
    return request('/api/prompts', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  remove(id) {
    return request(`/api/prompts/${id}`, { method: 'DELETE' })
  },
}

export const jobsApi = {
  create(body) {
    return request('/api/jobs', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  list(params = {}) {
    const q = new URLSearchParams(
      Object.fromEntries(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
      ),
    ).toString()
    return request(`/api/jobs?${q}`)
  },
  get(id) {
    return request(`/api/jobs/${id}`)
  },
  cancel(id) {
    return request(`/api/jobs/${id}/cancel`, { method: 'POST', body: '{}' })
  },
  retry(id) {
    return request(`/api/jobs/${id}/retry`, { method: 'POST', body: '{}' })
  },
}

export const ragApi = {
  stats() {
    return request('/api/rag/stats')
  },
  listCases(params = {}) {
    const q = new URLSearchParams()
    if (params.type) q.set('type', params.type)
    if (params.keyword) q.set('keyword', params.keyword)
    if (params.page) q.set('page', String(params.page))
    if (params.page_size) q.set('page_size', String(params.page_size))
    const qs = q.toString()
    return request(`/api/rag/cases${qs ? `?${qs}` : ''}`)
  },
  createCase(body) {
    return request('/api/rag/cases', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  deleteCase(id) {
    return request(`/api/rag/cases/${id}`, { method: 'DELETE' })
  },
  search(body) {
    return request('/api/rag/search', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  ingest(body) {
    return request('/api/rag/ingest', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
}

export const settingsApi = {
  getLlm() {
    return request('/api/settings/llm')
  },
  putLlm(payload) {
    return request('/api/settings/llm', {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
  testLlm() {
    return request('/api/settings/llm/test', { method: 'POST', body: '{}' })
  },
  getPaths() {
    return request('/api/settings/paths')
  },
  listOllamaModels() {
    return request('/api/settings/llm/ollama/models')
  },
}

export const monitorApi = {
  snapshot() {
    return request('/api/monitor/snapshot')
  },
  acestep() {
    return request('/api/monitor/acestep')
  },
}

export const projectsApi = {
  list(params = {}) {
    const q = new URLSearchParams()
    if (params.type) q.set('type', params.type)
    if (params.status) q.set('status', params.status)
    if (params.keyword) q.set('keyword', params.keyword)
    const qs = q.toString()
    return request(`/api/projects${qs ? `?${qs}` : ''}`)
  },
  get(id) {
    return request(`/api/projects/${id}`)
  },
  create(payload) {
    return request('/api/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  update(id, payload) {
    return request(`/api/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
  delete(id) {
    return request(`/api/projects/${id}`, { method: 'DELETE' })
  },
  complete(id) {
    return request(`/api/projects/${id}/complete`, { method: 'POST', body: '{}' })
  },
}

export const scriptsApi = {
  listScenes(projectId) {
    return request(`/api/scripts/${projectId}/scenes`)
  },
  updateScene(projectId, sceneId, payload) {
    return request(`/api/scripts/${projectId}/scenes/${sceneId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
  expand(payload) {
    return request('/api/scripts/expand', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  analyze(payload) {
    return request('/api/scripts/analyze', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  suggestions(projectId) {
    return request(`/api/scripts/${projectId}/suggest`, {
      method: 'POST',
    })
  },
}

export const storyboardApi = {
  list(projectId) {
    return request(`/api/storyboard/${projectId}/frames`)
  },
  get(projectId, frameId) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}`)
  },
  update(projectId, frameId, payload) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
  createFrame(projectId, payload = {}) {
    return request(`/api/storyboard/${projectId}/frames`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  deleteFrame(projectId, frameId) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}`, {
      method: 'DELETE',
    })
  },
  generate(projectId, frameId, payload = {}) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}/generate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  renderState(projectId, frameId) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}/render-state`)
  },
  submitRender(projectId, frameId, payload = {}) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}/render`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  acceptRender(projectId, frameId, attemptId) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}/render-attempts/${attemptId}/accept`, {
      method: 'POST',
      body: '{}',
    })
  },
  rejectRender(projectId, frameId, attemptId, payload) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}/render-attempts/${attemptId}/reject`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  retryRender(projectId, frameId, attemptId, reuseSeed = false) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}/render-attempts/${attemptId}/retry`, {
      method: 'POST',
      body: JSON.stringify({ reuse_seed: reuseSeed }),
    })
  },
  generateVideo(projectId, frameId, payload = {}) {
    return request(`/api/storyboard/${projectId}/frames/${frameId}/generate-video`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  consistencyCheck(projectId) {
    return request(`/api/storyboard/${projectId}/consistency-check`, {
      method: 'POST',
    })
  },
}

export const renderApi = {
  episodes(projectId) {
    return request(`/api/render/${projectId}/episodes`)
  },
  start(projectId, body) {
    return request(`/api/render/${projectId}/render`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  renders(projectId) {
    return request(`/api/render/${projectId}/renders`)
  },
  status(projectId, taskId) {
    return request(`/api/render/${projectId}/render/${taskId}/status`)
  },
}

export const ttsApi = {
  settings() {
    return request('/api/tts/settings')
  },
  saveSettings(body) {
    return request('/api/tts/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    })
  },
  test(engine) {
    return request('/api/tts/test', {
      method: 'POST',
      body: JSON.stringify({ engine }),
    })
  },
}
