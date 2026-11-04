<template>
  <div class="model-settings-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">模型设置</h1>
      <p class="page-desc">管理自定义模型供应商，配置后可在聊天时选择使用。</p>
      <div class="header-actions">
        <el-button :icon="Refresh" circle @click="loadProviders" />
        <el-button type="primary" @click="showAddProvider = true">
          <el-icon><Plus /></el-icon> 添加供应商
        </el-button>
      </div>
    </div>

    <!-- 主体：左侧供应商列表 + 右侧配置面板 -->
    <div class="settings-body">
      <!-- 左侧：供应商列表 -->
      <div class="provider-sidebar">
        <div class="sidebar-group-label" v-if="builtinProviders.length">内置</div>
        <div
          v-for="p in builtinProviders"
          :key="p.provider_id"
          class="provider-item"
          :class="{ active: selectedProviderId === p.provider_id }"
          @click="selectProvider(p.provider_id)"
        >
          <span class="provider-icon">{{ providerIcon(p.provider_id) }}</span>
          <span class="provider-name">{{ p.provider_name }}</span>
          <span class="status-dot" :class="p.enabled ? 'green' : 'orange'"></span>
        </div>

        <div class="sidebar-group-label" v-if="customProviders.length">自定义供应商</div>
        <div
          v-for="p in customProviders"
          :key="p.provider_id"
          class="provider-item"
          :class="{ active: selectedProviderId === p.provider_id }"
          @click="selectProvider(p.provider_id)"
        >
          <span class="provider-icon">📦</span>
          <span class="provider-name">{{ p.provider_name }}</span>
          <span class="status-dot" :class="p.enabled ? 'green' : 'orange'"></span>
        </div>
      </div>

      <!-- 右侧：配置面板 -->
      <div class="provider-detail" v-if="currentProvider">
        <!-- 供应商头部 -->
        <div class="detail-header">
          <div class="detail-title">
            <span class="provider-icon-large">{{ providerIcon(currentProvider.provider_id) }}</span>
            <h2>{{ currentProvider.provider_name }}</h2>
          </div>
          <div class="detail-actions">
            <el-switch
              v-model="currentProvider.enabled"
              @change="handleToggle"
            />
            <el-dropdown @command="handleDetailAction" v-if="!isBuiltin">
              <el-button text><el-icon><MoreFilled /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="test">测试连接</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除供应商</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <!-- Base URL -->
        <div class="form-group">
          <label class="form-label">Base URL</label>
          <el-input
            v-model="currentProvider.base_url"
            placeholder="https://api.deepseek.com/v1"
            @blur="handleSave"
          />
        </div>

        <!-- API 格式 -->
        <div class="form-group">
          <label class="form-label">API 格式</label>
          <el-select
            v-model="currentProvider.api_format"
            placeholder="选择API格式"
            style="width: 100%"
            @change="handleSave"
          >
            <el-option label="OpenAI Chat Completions (/v1/chat/completions)" value="openai_chat" />
            <el-option label="Anthropic Messages (/v1/messages)" value="anthropic_messages" />
            <el-option label="Google Generative AI" value="google_genai" />
            <el-option label="自定义格式" value="custom" />
          </el-select>
        </div>

        <!-- API Key -->
        <div class="form-group">
          <label class="form-label">API Key</label>
          <el-input
            v-model="currentProvider.api_key"
            type="password"
            show-password
            placeholder="输入 API Key"
            @blur="handleSave"
          />
        </div>

        <!-- 模型列表 -->
        <div class="form-group">
          <div class="model-list-header">
            <label class="form-label" style="margin:0">模型列表</label>
            <el-button size="small" @click="showAddModel = true">
              <el-icon><Plus /></el-icon> 添加模型
            </el-button>
          </div>

          <div class="model-list">
            <div
              v-for="(model, idx) in currentProvider.models"
              :key="idx"
              class="model-item"
            >
              <span class="model-name">{{ model.model_id }}</span>
              <div class="model-tags">
                <el-tag size="small" type="info" v-if="model.max_context >= 100000">
                  {{ Math.round(model.max_context / 1000) }}K
                </el-tag>
                <el-tag size="small" v-if="model.has_vision">视觉</el-tag>
              </div>
              <div class="model-actions">
                <el-button text size="small" @click="editModel(idx)">
                  <el-icon><Edit /></el-icon>
                </el-button>
                <el-button text size="small" type="danger" @click="removeModel(idx)">
                  <el-icon><Delete /></el-icon>
                </el-button>
                <el-switch
                  v-model="model.enabled"
                  size="small"
                  @change="handleSave"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 未选择供应商时的空状态 -->
      <div class="provider-empty" v-else>
        <el-empty description="从左侧选择供应商以查看详情" />
      </div>
    </div>

    <!-- 添加供应商对话框 -->
    <el-dialog v-model="showAddProvider" title="添加供应商" width="560px">
      <el-form :model="newProvider" label-width="100px">
        <el-form-item label="供应商名称">
          <el-input v-model="newProvider.provider_name" placeholder="如：DeepSeek" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="newProvider.base_url" placeholder="https://api.example.com/v1" />
        </el-form-item>
        <el-form-item label="API 格式">
          <el-select v-model="newProvider.api_format" style="width:100%">
            <el-option label="OpenAI Chat Completions" value="openai_chat" />
            <el-option label="Anthropic Messages" value="anthropic_messages" />
            <el-option label="自定义格式" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="newProvider.api_key" type="password" show-password placeholder="sk-..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddProvider = false">取消</el-button>
        <el-button type="primary" @click="handleAddProvider">确认添加</el-button>
      </template>
    </el-dialog>

    <!-- 添加/编辑模型对话框 -->
    <el-dialog v-model="showAddModel" :title="editingModelIdx >= 0 ? '编辑模型' : '添加模型'" width="480px">
      <el-form :model="editingModel" label-width="100px">
        <el-form-item label="模型ID">
          <el-input v-model="editingModel.model_id" placeholder="如 deepseek-coder" />
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="editingModel.model_name" placeholder="如 DeepSeek Coder" />
        </el-form-item>
        <el-form-item label="上下文长度">
          <el-input-number v-model="editingModel.max_context" :min="1024" :step="4096" />
        </el-form-item>
        <el-form-item label="支持视觉">
          <el-switch v-model="editingModel.has_vision" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddModel = false">取消</el-button>
        <el-button type="primary" @click="handleSaveModel">确认</el-button>
      </template>
    </el-dialog>

    <!-- 测试连接结果对话框 -->
    <el-dialog v-model="showTestResult" title="连接测试结果" width="400px">
      <el-result
        :icon="testResultSuccess ? 'success' : 'error'"
        :title="testResultSuccess ? '连接成功' : '连接失败'"
        :sub-title="testResultMessage"
      />
    </el-dialog>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Edit, Delete, MoreFilled } from '@element-plus/icons-vue'
import { listProviders, createProvider, updateProvider, deleteProvider, toggleProvider, testProviderConnection } from '../api/llm.js'

const PROVIDER_ICONS = {
  deepseek: '',
  openai: '🟢',
  qwen: '🔵',
  zhipu: '',
  custom: '',
}

export default {
  name: 'ModelSettingsView',
  setup() {
    const providers = ref([])
    const selectedProviderId = ref('')
    const showAddProvider = ref(false)
    const showAddModel = ref(false)
    const showTestResult = ref(false)
    const testResultSuccess = ref(false)
    const testResultMessage = ref('')
    const editingModelIdx = ref(-1)

    const newProvider = ref({
      provider_name: '',
      base_url: '',
      api_format: 'openai_chat',
      api_key: '',
    })

    const editingModel = ref({
      model_id: '',
      model_name: '',
      max_context: 16384,
      has_vision: false,
      enabled: true,
    })

    const builtinProviders = computed(() =>
      providers.value.filter(p => p.provider_type === 'builtin')
    )
    const customProviders = computed(() =>
      providers.value.filter(p => p.provider_type === 'custom')
    )
    const isBuiltin = computed(() => {
      const p = providers.value.find(p => p.provider_id === selectedProviderId.value)
      return p && p.provider_type === 'builtin'
    })
    const currentProvider = computed(() =>
      providers.value.find(p => p.provider_id === selectedProviderId.value)
    )

    async function loadProviders() {
      try {
        const res = await listProviders()
        providers.value = res.data.providers
        if (!selectedProviderId.value && providers.value.length) {
          selectedProviderId.value = providers.value[0].provider_id
        }
      } catch (err) {
        ElMessage.error('加载供应商列表失败')
      }
    }

    function selectProvider(id) {
      selectedProviderId.value = id
    }

    function providerIcon(id) {
      return PROVIDER_ICONS[id] || '📦'
    }

    async function handleToggle() {
      if (!currentProvider.value) return
      try {
        const res = await toggleProvider(currentProvider.value.provider_id)
        currentProvider.value.enabled = res.data.provider.enabled
        ElMessage.success(currentProvider.value.enabled ? '已启用' : '已禁用')
      } catch (err) {
        ElMessage.error('操作失败')
      }
    }

    async function handleSave() {
      if (!currentProvider.value || isBuiltin.value) return
      try {
        await updateProvider(currentProvider.value.provider_id, {
          base_url: currentProvider.value.base_url,
          api_format: currentProvider.value.api_format,
          api_key: currentProvider.value.api_key,
          models: currentProvider.value.models,
        })
      } catch (err) {
        // 静默保存
      }
    }

    async function handleAddProvider() {
      if (!newProvider.value.provider_name) {
        ElMessage.warning('请输入供应商名称')
        return
      }
      try {
        const res = await createProvider({
          ...newProvider.value,
          models: [{
            model_id: 'default',
            model_name: 'Default Model',
            max_context: 16384,
            has_vision: false,
            enabled: true,
          }],
        })
        providers.value.push(res.data.provider)
        selectedProviderId.value = res.data.provider.provider_id
        showAddProvider.value = false
        newProvider.value = { provider_name: '', base_url: '', api_format: 'openai_chat', api_key: '' }
        ElMessage.success('供应商已添加')
      } catch (err) {
        ElMessage.error('添加失败')
      }
    }

    async function handleDetailAction(command) {
      if (!currentProvider.value) return
      if (command === 'test') {
        await testConnection()
      } else if (command === 'delete') {
        try {
          await ElMessageBox.confirm('确定删除此供应商？', '提示', { type: 'warning' })
          await deleteProvider(currentProvider.value.provider_id)
          providers.value = providers.value.filter(p => p.provider_id !== currentProvider.value.provider_id)
          selectedProviderId.value = providers.value[0]?.provider_id || ''
          ElMessage.success('已删除')
        } catch (err) {
          if (err !== 'cancel') ElMessage.error('删除失败')
        }
      }
    }

    async function testConnection() {
      if (!currentProvider.value) return
      try {
        const res = await testProviderConnection({
          base_url: currentProvider.value.base_url,
          api_format: currentProvider.value.api_format,
          api_key: currentProvider.value.api_key,
          model: currentProvider.value.models[0]?.model_id || '',
        })
        testResultSuccess.value = true
        testResultMessage.value = res.data.response
      } catch (err) {
        testResultSuccess.value = false
        testResultMessage.value = err.response?.data?.detail || err.message
      }
      showTestResult.value = true
    }

    function editModel(idx) {
      editingModelIdx.value = idx
      const m = currentProvider.value.models[idx]
      editingModel.value = { ...m }
      showAddModel.value = true
    }

    function removeModel(idx) {
      currentProvider.value.models.splice(idx, 1)
      handleSave()
    }

    function handleSaveModel() {
      if (!editingModel.value.model_id) {
        ElMessage.warning('请输入模型ID')
        return
      }
      if (editingModelIdx.value >= 0) {
        // 编辑模式
        Object.assign(currentProvider.value.models[editingModelIdx.value], editingModel.value)
      } else {
        // 新增模式
        currentProvider.value.models.push({ ...editingModel.value })
      }
      handleSave()
      showAddModel.value = false
      editingModelIdx.value = -1
      editingModel.value = { model_id: '', model_name: '', max_context: 16384, has_vision: false, enabled: true }
    }

    onMounted(loadProviders)

    return {
      providers, selectedProviderId,
      builtinProviders, customProviders, isBuiltin, currentProvider,
      showAddProvider, showAddModel, showTestResult,
      testResultSuccess, testResultMessage,
      newProvider, editingModel, editingModelIdx,
      loadProviders, selectProvider, providerIcon,
      handleToggle, handleSave, handleAddProvider, handleDetailAction,
      editModel, removeModel, handleSaveModel,
      Plus, Refresh, Edit, Delete, MoreFilled,
    }
  },
}
</script>

<style scoped>
.model-settings-view {
  max-width: 1200px;
  margin: 0 auto;
  min-height: 600px;
}

/* 页面头部 */
.page-header {
  margin-bottom: 24px;
}
.page-title {
  font-size: 28px;
  font-weight: 700;
  color: #e5e7eb;
  margin-bottom: 8px;
}
.page-desc {
  font-size: 14px;
  color: #9ca3af;
  margin-bottom: 16px;
}
.header-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

/* 主体布局 */
.settings-body {
  display: flex;
  background: #1e1e1e;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid #333;
  min-height: 520px;
}

/* 左侧供应商列表 */
.provider-sidebar {
  width: 220px;
  background: #252525;
  border-right: 1px solid #333;
  padding: 12px 0;
  flex-shrink: 0;
  overflow-y: auto;
}
.sidebar-group-label {
  padding: 8px 16px 4px;
  font-size: 12px;
  color: #6b7280;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.provider-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s;
  color: #d1d5db;
}
.provider-item:hover {
  background: #333;
}
.provider-item.active {
  background: #374151;
  color: #fff;
}
.provider-icon {
  font-size: 16px;
  width: 24px;
  text-align: center;
}
.provider-name {
  flex: 1;
  font-size: 14px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.green { background: #22c55e; }
.status-dot.orange { background: #f97316; }

/* 右侧配置面板 */
.provider-detail {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
  background: #2a2a2a;
}
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.detail-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.provider-icon-large {
  font-size: 28px;
}
.detail-title h2 {
  font-size: 22px;
  font-weight: 600;
  color: #e5e7eb;
  margin: 0;
}
.detail-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 表单 */
.form-group {
  margin-bottom: 20px;
}
.form-label {
  display: block;
  font-size: 13px;
  color: #9ca3af;
  margin-bottom: 8px;
  font-weight: 500;
}

/* 模型列表 */
.model-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.model-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.model-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: #333;
  border-radius: 8px;
  transition: background 0.15s;
}
.model-item:hover {
  background: #3a3a3a;
}
.model-name {
  flex: 1;
  font-size: 14px;
  font-family: 'Consolas', 'Monaco', monospace;
  color: #e5e7eb;
}
.model-tags {
  display: flex;
  gap: 4px;
}
.model-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 空状态 */
.provider-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #2a2a2a;
}

/* 覆盖 Element Plus 深色主题 */
:deep(.el-input__wrapper) {
  background: #333;
  border: 1px solid #444;
  box-shadow: none;
}
:deep(.el-input__inner) {
  color: #e5e7eb;
}
:deep(.el-select .el-input__wrapper) {
  background: #333;
}
:deep(.el-form-item__label) {
  color: #9ca3af;
}
</style>
