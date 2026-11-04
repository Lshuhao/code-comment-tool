<template>
  <el-config-provider :locale="zhCn">
    <div id="app-root">
      <el-container>
        <el-header class="app-header">
          <div class="header-left">
            <el-icon :size="24"><Document /></el-icon>
            <span class="app-title">代码注释自动生成与优化建议工具</span>
          </div>
          <el-menu mode="horizontal" :default-active="activeMenu" router>
            <el-menu-item index="/">代码分析</el-menu-item>
            <el-menu-item index="/history">历史记录</el-menu-item>
            <el-menu-item index="/model-settings">模型设置</el-menu-item>
          </el-menu>
        </el-header>
        <el-main class="app-main">
          <router-view />
        </el-main>
      </el-container>
    </div>
  </el-config-provider>
</template>

<script>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'

export default {
  name: 'App',
  setup() {
    const route = useRoute()
    const activeMenu = computed(() => route.path)
    return { activeMenu, zhCn }
  },
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; }
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 24px;
  height: 56px !important;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.app-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.app-main {
  background: #f5f7fa;
  min-height: calc(100vh - 56px);
  padding: 20px;
}
</style>
