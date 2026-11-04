<template>
  <el-card class="score-overview" shadow="hover">
    <el-row :gutter="20">
      <!-- 总评分 -->
      <el-col :span="6">
        <div class="total-score">
          <div class="score-circle" :style="{ borderColor: scoreColor }">
            <span class="score-number" :style="{ color: scoreColor }">
              {{ score?.score?.toFixed(1) || '-' }}
            </span>
            <span class="score-label">综合评分</span>
          </div>
          <div class="score-level" :style="{ color: scoreColor }">
            {{ scoreLevel }}
          </div>
        </div>
      </el-col>

      <!-- 四维度评分 -->
      <el-col :span="18">
        <div class="dimensions-grid">
          <div v-for="(dim, key) in dimensionConfig" :key="key" class="dimension-item">
            <div class="dim-header">
              <span class="dim-icon">{{ dim.icon }}</span>
              <span class="dim-name">{{ dim.label }}</span>
              <span class="dim-value" :style="{ color: dimColor(dimensions?.[key] || 0) }">
                {{ (dimensions?.[key] || 0).toFixed(1) }}%
              </span>
            </div>
            <el-progress
              :percentage="dimensions?.[key] || 0"
              :color="dimColor(dimensions?.[key] || 0)"
              :stroke-width="10"
              :show-text="false"
            />
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 评分摘要 -->
    <div class="score-summary" v-if="score?.summary">
      <el-icon><InfoFilled /></el-icon>
      <span>{{ score.summary }}</span>
    </div>
  </el-card>
</template>

<script>
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'

export default {
  name: 'ScoreOverview',
  components: { InfoFilled },
  props: {
    score: Object,
    dimensions: Object,
  },
  setup(props) {
    const dimensionConfig = {
      coverage: { label: '注释覆盖率', icon: '📝' },
      completeness: { label: '文档完整性', icon: '📋' },
      consistency: { label: '风格一致性', icon: '🎨' },
      standard: { label: '规范符合度', icon: '✅' },
    }

    const scoreColor = computed(() => {
      const s = props.score?.score || 0
      if (s >= 90) return '#22c55e'
      if (s >= 75) return '#3b82f6'
      if (s >= 60) return '#f59e0b'
      return '#ef4444'
    })

    const scoreLevel = computed(() => {
      const s = props.score?.score || 0
      if (s >= 90) return '优秀'
      if (s >= 75) return '良好'
      if (s >= 60) return '一般'
      return '需要改进'
    })

    function dimColor(value) {
      if (value >= 80) return '#22c55e'
      if (value >= 60) return '#3b82f6'
      if (value >= 40) return '#f59e0b'
      return '#ef4444'
    }

    return { dimensionConfig, scoreColor, scoreLevel, dimColor }
  },
}
</script>

<style scoped>
.score-overview { margin-bottom: 20px; }
.total-score { text-align: center; }
.score-circle {
  width: 120px; height: 120px;
  border-radius: 50%;
  border: 4px solid #e4e7ed;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  margin: 0 auto 8px;
}
.score-number { font-size: 32px; font-weight: bold; }
.score-label { font-size: 12px; color: #909399; }
.score-level { font-size: 14px; font-weight: 600; }
.dimensions-grid { display: flex; flex-direction: column; gap: 16px; padding-top: 8px; }
.dimension-item { }
.dim-header {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 6px;
}
.dim-icon { font-size: 18px; }
.dim-name { font-size: 14px; color: #606266; flex: 1; }
.dim-value { font-size: 16px; font-weight: bold; }
.score-summary {
  margin-top: 16px; padding: 12px;
  background: #f0f9ff; border-radius: 6px;
  display: flex; align-items: center; gap: 8px;
  color: #3b82f6; font-size: 14px;
}
</style>
