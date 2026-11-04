<template>
  <el-card shadow="hover" class="defect-panel">
    <template #header>
      <div class="card-header">
        <span>🔍 缺陷检测 ({{ defects.length }})</span>
      </div>
    </template>

    <div v-if="defects.length === 0" class="empty-state">
      <el-result icon="success" title="未检测到缺陷" sub-title="代码注释质量良好" />
    </div>

    <div v-else class="defect-list">
      <!-- 按严重程度分组统计 -->
      <div class="defect-stats">
        <div class="stat-item" v-for="stat in severityStats" :key="stat.level">
          <span class="stat-dot" :style="{ background: stat.color }"></span>
          <span class="stat-label">{{ stat.label }}</span>
          <span class="stat-count">{{ stat.count }}</span>
        </div>
      </div>

      <!-- 缺陷列表 -->
      <el-collapse accordion class="defect-collapse">
        <el-collapse-item
          v-for="(defect, index) in defects"
          :key="defect.defect_id"
          :name="index"
        >
          <template #title>
            <div class="defect-title">
              <el-tag :type="severityTagType(defect.severity)" size="small">
                {{ severityLabel(defect.severity) }}
              </el-tag>
              <span class="defect-desc">{{ defect.description }}</span>
            </div>
          </template>
          <div class="defect-detail">
            <p><strong>位置:</strong> {{ defect.location }}</p>
            <p><strong>类型:</strong> {{ defectTypeLabel(defect.type) }}</p>
            <p><strong>检测层:</strong> {{ defect.detection_layer === 'rule' ? '规则层' : '语义层' }}</p>
            <p v-if="defect.suggested_fix"><strong>建议:</strong> {{ defect.suggested_fix }}</p>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </el-card>
</template>

<script>
import { computed } from 'vue'

export default {
  name: 'DefectPanel',
  props: {
    defects: { type: Array, default: () => [] },
  },
  setup(props) {
    const severityStats = computed(() => {
      const counts = { error: 0, warning: 0, info: 0 }
      props.defects.forEach(d => { counts[d.severity] = (counts[d.severity] || 0) + 1 })
      return [
        { level: 'error', label: '错误', count: counts.error, color: '#ef4444' },
        { level: 'warning', label: '警告', count: counts.warning, color: '#f59e0b' },
        { level: 'info', label: '提示', count: counts.info, color: '#3b82f6' },
      ].filter(s => s.count > 0)
    })

    function severityLabel(s) {
      return { error: '错误', warning: '警告', info: '提示' }[s] || s
    }

    function severityTagType(s) {
      return { error: 'danger', warning: 'warning', info: 'info' }[s] || ''
    }

    function defectTypeLabel(t) {
      return {
        missing_docstring: '缺少文档字符串',
        missing_param_doc: '缺少参数文档',
        missing_return_doc: '缺少返回值文档',
        bad_format: '格式不规范',
        redundant_comment: '冗余注释',
        outdated_comment: '过期注释',
        inconsistent_comment: '不一致注释',
        todo_comment: 'TODO注释',
        commented_out_code: '被注释的代码',
      }[t] || t
    }

    return { severityStats, severityLabel, severityTagType, defectTypeLabel }
  },
}
</script>

<style scoped>
.defect-panel { margin-bottom: 20px; }
.card-header { font-weight: 600; }
.defect-stats {
  display: flex; gap: 16px;
  padding: 12px; margin-bottom: 12px;
  background: #f8fafc; border-radius: 6px;
}
.stat-item { display: flex; align-items: center; gap: 6px; }
.stat-dot { width: 8px; height: 8px; border-radius: 50%; }
.stat-label { font-size: 13px; color: #606266; }
.stat-count { font-weight: bold; color: #303133; }
.defect-collapse { }
.defect-title { display: flex; align-items: center; gap: 8px; }
.defect-desc { font-size: 13px; color: #606266; }
.defect-detail { font-size: 13px; color: #606266; line-height: 1.8; }
.defect-detail strong { color: #303133; }
.empty-state { padding: 20px 0; }
</style>
