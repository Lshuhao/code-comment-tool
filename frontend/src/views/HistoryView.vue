<template>
  <div class="history-view">
    <el-card shadow="hover">
      <template #header>
        <span class="card-title">📋 分析历史记录</span>
      </template>

      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column prop="filename" label="文件名" width="200" />
        <el-table-column prop="language" label="语言" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="langTagType(row.language)">{{ row.language }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="score" label="评分" width="100">
          <template #default="{ row }">
            <span :style="{ color: scoreColor(row.score), fontWeight: 'bold' }">
              {{ row.score?.toFixed(1) || '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="suggestions_count" label="建议数" width="100" />
        <el-table-column prop="defects_count" label="缺陷数" width="100" />
        <el-table-column prop="created_at" label="分析时间" width="200" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewDetail(row)">
              查看详情
            </el-button>
            <el-button type="danger" link size="small" @click="deleteTask(row.task_id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="total > pageSize"
        :total="total"
        :page-size="pageSize"
        v-model:current-page="currentPage"
        layout="prev, pager, next"
        @current-change="loadHistory"
        style="margin-top: 16px; justify-content: center;"
      />
    </el-card>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listTasks } from '../api/index.js'

export default {
  name: 'HistoryView',
  setup() {
    const tasks = ref([])
    const loading = ref(false)
    const total = ref(0)
    const currentPage = ref(1)
    const pageSize = 20

    async function loadHistory() {
      loading.value = true
      try {
        const res = await listTasks()
        tasks.value = res.data.tasks || []
        total.value = res.data.total || 0
      } catch (err) {
        ElMessage.error('加载历史记录失败')
      } finally {
        loading.value = false
      }
    }

    function viewDetail(row) {
      ElMessage.info(`查看任务 ${row.task_id} 的详情（功能开发中）`)
    }

    function deleteTask(taskId) {
      ElMessageBox.confirm('确定删除此记录？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }).then(() => {
        ElMessage.success('已删除')
        loadHistory()
      }).catch(() => {})
    }

    function scoreColor(score) {
      if (score >= 90) return '#22c55e'
      if (score >= 75) return '#3b82f6'
      if (score >= 60) return '#f59e0b'
      return '#ef4444'
    }

    function langTagType(lang) {
      return { python: 'success', java: 'warning', cpp: 'info' }[lang] || ''
    }

    onMounted(loadHistory)

    return {
      tasks, loading, total, currentPage, pageSize,
      loadHistory, viewDetail, deleteTask, scoreColor, langTagType,
    }
  },
}
</script>

<style scoped>
.history-view { max-width: 1200px; margin: 0 auto; }
.card-title { font-size: 18px; font-weight: 600; }
</style>
