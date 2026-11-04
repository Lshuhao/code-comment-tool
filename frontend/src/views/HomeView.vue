<template>
  <div class="home-view">
    <!-- 输入区域 -->
    <el-card class="input-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>代码输入</span>
          <div class="header-actions">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".py,.java,.cpp,.c,.h,.hpp"
              :on-change="handleFileUpload"
            >
              <el-button :icon="Upload">上传文件</el-button>
            </el-upload>
            <el-select v-model="selectedLanguage" placeholder="语言（自动检测）" clearable style="width: 160px">
              <el-option label="Python" value="python" />
              <el-option label="Java" value="java" />
              <el-option label="C++" value="cpp" />
            </el-select>
          </div>
        </div>
      </template>

      <el-input
        v-model="codeInput"
        type="textarea"
        :rows="12"
        placeholder="在此粘贴代码，或上传文件..."
        class="code-input"
      />

      <div class="input-footer">
        <span class="file-info" v-if="currentFilename">
          📄 {{ currentFilename }} | {{ codeInput.split('\n').length }} 行
        </span>
        <el-button
          type="primary"
          :loading="analyzing"
          :disabled="!codeInput.trim()"
          @click="startAnalysis"
          size="large"
        >
          {{ analyzing ? '分析中...' : '开始分析' }}
        </el-button>
      </div>
    </el-card>

    <!-- 分析结果 -->
    <div v-if="taskResult" class="result-section">
      <!-- 评分概览 -->
      <ScoreOverview :score="taskResult.score" :dimensions="taskResult.score?.dimensions" />

      <!-- 双栏对比 -->
      <el-card class="diff-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>代码对比</span>
            <div class="header-actions">
              <el-button-group>
                <el-button
                  :type="viewMode === 'diff' ? 'primary' : ''"
                  @click="viewMode = 'diff'"
                  size="small"
                >Diff视图</el-button>
                <el-button
                  :type="viewMode === 'side' ? 'primary' : ''"
                  @click="viewMode = 'side'"
                  size="small"
                >并排视图</el-button>
              </el-button-group>
              <el-dropdown @command="handleExport">
                <el-button size="small">
                  导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="source">源代码</el-dropdown-item>
                    <el-dropdown-item command="markdown">Markdown报告</el-dropdown-item>
                    <el-dropdown-item command="html">HTML报告</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </template>

        <MonacoDiffViewer
          :original="originalCode"
          :modified="annotatedCode || originalCode"
          :language="detectedLanguage"
          :view-mode="viewMode"
        />
      </el-card>

      <!-- 建议列表 -->
      <el-row :gutter="20">
        <el-col :span="16">
          <SuggestionList
            :suggestions="taskResult.suggestions"
            :accepted-ids="acceptedIds"
            @accept="handleAccept"
            @reject="handleReject"
            @accept-all="handleAcceptAll"
          />
        </el-col>
        <el-col :span="8">
          <DefectPanel :defects="taskResult.defects" />
        </el-col>
      </el-row>
    </div>

    <!-- 空状态 -->
    <el-empty v-else-if="!analyzing" description="上传或粘贴代码，点击「开始分析」" />
  </div>
</template>

<script>
import { ref, computed } from 'vue'
import { Upload, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { analyzeText, acceptSuggestions, rejectSuggestions, exportResult } from '../api/index.js'
import ScoreOverview from '../components/ScoreOverview.vue'
import MonacoDiffViewer from '../components/MonacoDiffViewer.vue'
import SuggestionList from '../components/SuggestionList.vue'
import DefectPanel from '../components/DefectPanel.vue'

export default {
  name: 'HomeView',
  components: { ScoreOverview, MonacoDiffViewer, SuggestionList, DefectPanel },
  setup() {
    const codeInput = ref('')
    const selectedLanguage = ref('')
    const currentFilename = ref('')
    const analyzing = ref(false)
    const taskResult = ref(null)
    const viewMode = ref('diff')
    const acceptedIds = ref([])

    const originalCode = computed(() => codeInput.value)
    const detectedLanguage = computed(() => taskResult.value?.ingest?.language || 'python')
    const annotatedCode = computed(() => taskResult.value?.annotated_code || '')

    async function handleFileUpload(file) {
      const reader = new FileReader()
      reader.onload = (e) => {
        codeInput.value = e.target.result
        currentFilename.value = file.name
      }
      reader.readAsText(file.raw)
    }

    async function startAnalysis() {
      if (!codeInput.value.trim()) return
      analyzing.value = true
      try {
        const res = await analyzeText(
          codeInput.value,
          currentFilename.value || 'untitled.py',
          selectedLanguage.value || null
        )
        taskResult.value = res.data
        ElMessage.success('分析完成')
      } catch (err) {
        ElMessage.error('分析失败: ' + (err.response?.data?.detail || err.message))
      } finally {
        analyzing.value = false
      }
    }

    async function handleAccept(suggestionId) {
      acceptedIds.value.push(suggestionId)
      await refreshAnnotatedCode()
    }

    async function handleReject(suggestionId) {
      const idx = acceptedIds.value.indexOf(suggestionId)
      if (idx > -1) acceptedIds.value.splice(idx, 1)
    }

    async function handleAcceptAll() {
      if (!taskResult.value) return
      const allIds = taskResult.value.suggestions.map(s => s.suggestion_id)
      acceptedIds.value = allIds
      await refreshAnnotatedCode()
    }

    async function refreshAnnotatedCode() {
      if (!taskResult.value || acceptedIds.value.length === 0) return
      try {
        const res = await acceptSuggestions(taskResult.value.task_id, acceptedIds.value)
        taskResult.value.annotated_code = res.data.annotated_code
      } catch (err) {
        // 静默处理
      }
    }

    async function handleExport(format) {
      if (!taskResult.value) return
      try {
        const res = await exportResult(taskResult.value.task_id, format)
        const blob = new Blob([res.data])
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        const extMap = { source: 'py', markdown: 'md', html: 'html' }
        a.download = `report.${extMap[format] || 'txt'}`
        a.click()
        URL.revokeObjectURL(url)
        ElMessage.success('导出成功')
      } catch (err) {
        ElMessage.error('导出失败')
      }
    }

    return {
      codeInput, selectedLanguage, currentFilename, analyzing,
      taskResult, viewMode, acceptedIds, originalCode,
      detectedLanguage, annotatedCode,
      handleFileUpload, startAnalysis,
      handleAccept, handleReject, handleAcceptAll, handleExport,
      Upload, ArrowDown,
    }
  },
}
</script>

<style scoped>
.home-view { max-width: 1400px; margin: 0 auto; }
.input-card { margin-bottom: 20px; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}
.header-actions { display: flex; gap: 12px; align-items: center; }
.code-input { font-family: 'Consolas', 'Monaco', monospace; }
.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}
.file-info { color: #909399; font-size: 14px; }
.result-section { margin-top: 20px; }
.diff-card { margin-bottom: 20px; }
</style>
