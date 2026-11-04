/**
 * LLM 供应商管理 API
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 列出所有供应商
export function listProviders() {
  return api.get('/providers')
}

// 获取供应商详情
export function getProvider(providerId) {
  return api.get(`/providers/${providerId}`)
}

// 创建供应商
export function createProvider(data) {
  return api.post('/providers', data)
}

// 更新供应商
export function updateProvider(providerId, data) {
  return api.put(`/providers/${providerId}`, data)
}

// 删除供应商
export function deleteProvider(providerId) {
  return api.delete(`/providers/${providerId}`)
}

// 切换启用/禁用
export function toggleProvider(providerId) {
  return api.post(`/providers/${providerId}/toggle`)
}

// 获取所有可用模型
export function listAllModels() {
  return api.get('/providers/models')
}

// 测试供应商连接
export function testProviderConnection(data) {
  return api.post('/providers/test', data)
}
