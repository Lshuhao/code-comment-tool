<template>
  <el-card shadow="hover" class="suggestion-list-card">
    <template #header>
      <div class="card-header">
        <span>💡 注释建议 ({{ suggestions.length }})</span>
        <el-button type="primary" size="small" @click="$emit('accept-all')" :disabled="suggestions.length === 0">
          全部采纳
        </el-button>
      </div>
    </template>

    <div v-if="suggestions.length === 0" class="empty-state">
      <el-empty description="暂无注释建议" :image-size="80" />
    </div>

    <div v-else class="suggestions">
      <div
        v-for="(item, index) in suggestions"
        :key="item.suggestion_id"
        class="suggestion-item"
        :class="{ accepted: isAccepted(item.suggestion_id) }"
      >
        <div class="suggestion-header">
          <el-tag :type="typeTagColor(item.type)" size="small">
            {{ typeLabel(item.type) }}
          </el-tag>
          <span class="suggestion-line">第 {{ item.target_line }} 行</span>
          <el-tag v-if="item.confidence" size="small" type="info">
            置信度 {{ (item.confidence * 100).toFixed(0) }}%
          </el-tag>
          <div class="suggestion-actions">
            <el-button
              v-if="!isAccepted(item.suggestion_id)"
              type="success" link size="small"
              @click="$emit('accept', item.suggestion_id)"
            >
              ✓ 采纳
            </el-button>
            <el-tag v-else type="success" size="small">已采纳</el-tag>
            <el-button
              type="danger" link size="small"
              @click="$emit('reject', item.suggestion_id)"
            >
              ✗ 忽略
            </el-button>
          </div>
        </div>

        <div class="suggestion-content">
          <pre class="suggestion-text">{{ item.suggested_text }}</pre>
        </div>

        <div class="suggestion-reason" v-if="item.reasoning">
          {{ item.reasoning }}
        </div>
      </div>
    </div>
  </el-card>
</template>

<script>
export default {
  name: 'SuggestionList',
  props: {
    suggestions: { type: Array, default: () => [] },
    acceptedIds: { type: Array, default: () => [] },
  },
  emits: ['accept', 'reject', 'accept-all'],
  setup(props) {
    function isAccepted(id) {
      return props.acceptedIds.includes(id)
    }

    function typeLabel(type) {
      return {
        docstring: '文档字符串',
        inline_comment: '行内注释',
        block_comment: '块注释',
        improve_existing: '改进注释',
      }[type] || type
    }

    function typeTagColor(type) {
      return {
        docstring: 'primary',
        inline_comment: 'success',
        block_comment: 'warning',
        improve_existing: 'info',
      }[type] || ''
    }

    return { isAccepted, typeLabel, typeTagColor }
  },
}
</script>

<style scoped>
.suggestion-list-card { margin-bottom: 20px; }
.card-header {
  display: flex; align-items: center; justify-content: space-between;
  font-weight: 600;
}
.suggestions { max-height: 600px; overflow-y: auto; }
.suggestion-item {
  padding: 16px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  margin-bottom: 12px;
  transition: all 0.2s;
}
.suggestion-item:hover { border-color: #409eff; box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1); }
.suggestion-item.accepted { background: #f0fdf4; border-color: #86efac; }
.suggestion-header {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px; flex-wrap: wrap;
}
.suggestion-line { color: #909399; font-size: 13px; }
.suggestion-actions { margin-left: auto; display: flex; gap: 4px; }
.suggestion-content {
  background: #f8fafc; border-radius: 6px; padding: 12px;
  margin: 8px 0;
}
.suggestion-text {
  margin: 0; font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px; white-space: pre-wrap; word-break: break-all;
  color: #1e293b; line-height: 1.6;
}
.suggestion-reason {
  font-size: 12px; color: #909399; font-style: italic;
}
.empty-state { padding: 20px 0; }
</style>
