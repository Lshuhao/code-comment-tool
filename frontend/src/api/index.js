/**
 * API客户端 - 封装后端接口调用
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

// 上传文件分析
export function uploadFile(file, sessionId = null) {
  const formData = new FormData()
  formData.append('file', file)
  if (sessionId) formData.append('session_id', sessionId)
  return api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 分析粘贴文本
export function analyzeText(code, filename = 'untitled.py', language = null) {
  const formData = new FormData()
  formData.append('code', code)
  formData.append('filename', filename)
  if (language) formData.append('language', language)
  return api.post('/analyze', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 获取任务详情
export function getTask(taskId) {
  return api.get(`/task/${taskId}`)
}

// 获取任务列表
export function listTasks() {
  return api.get('/tasks')
}

// 获取建议列表
export function getSuggestions(taskId) {
  return api.get(`/task/${taskId}/suggestions`)
}

// 采纳建议
export function acceptSuggestions(taskId, suggestionIds) {
  return api.post(`/task/${taskId}/accept`, suggestionIds)
}

// 拒绝建议
export function rejectSuggestions(taskId, suggestionIds) {
  return api.post(`/task/${taskId}/reject`, suggestionIds)
}

// 获取缺陷列表
export function getDefects(taskId) {
  return api.get(`/task/${taskId}/defects`)
}

// 获取评分
export function getScore(taskId) {
  return api.get(`/task/${taskId}/score`)
}

// 导出结果
export function exportResult(taskId, format) {
  return api.get(`/task/${taskId}/export/${format}`, { responseType: 'blob' })
}

// 健康检查
export function healthCheck() {
  return api.get('/health')
}

export default api
