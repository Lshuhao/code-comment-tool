<template>
  <div class="monaco-diff-viewer">
    <div ref="editorContainer" class="editor-container" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

// Monaco Editor语言映射
const LANGUAGE_MAP = {
  python: 'python',
  java: 'java',
  cpp: 'cpp',
  c: 'cpp',
}

export default {
  name: 'MonacoDiffViewer',
  props: {
    original: { type: String, default: '' },
    modified: { type: String, default: '' },
    language: { type: String, default: 'python' },
    viewMode: { type: String, default: 'diff' }, // 'diff' | 'side'
    height: { type: Number, default: 500 },
  },
  setup(props) {
    const editorContainer = ref(null)
    let editor = null
    let monacoInstance = null

    async function initEditor() {
      if (!editorContainer.value) return

      // 动态加载monaco-editor
      const monaco = await import('monaco-editor')
      monacoInstance = monaco

      const lang = LANGUAGE_MAP[props.language] || 'plaintext'

      if (props.viewMode === 'diff') {
        createDiffEditor(monaco, lang)
      } else {
        createSideBySide(monaco, lang)
      }
    }

    function createDiffEditor(monaco, lang) {
      if (editor) { editor.dispose() }

      editor = monaco.editor.createDiffEditor(editorContainer.value, {
        theme: 'vs-light',
        readOnly: true,
        renderSideBySide: true,
        minimap: { enabled: false },
        fontSize: 14,
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
        originalEditable: false,
      })

      const originalModel = monaco.editor.createModel(props.original, lang)
      const modifiedModel = monaco.editor.createModel(props.modified, lang)

      editor.setModel({ original: originalModel, modified: modifiedModel })
    }

    function createSideBySide(monaco, lang) {
      if (editor) { editor.dispose() }

      // 并排模式用两个普通编辑器
      editorContainer.value.innerHTML = `
        <div style="display:flex; height:100%; gap:4px;">
          <div style="flex:1; border:1px solid #e4e7ed; border-radius:4px; overflow:hidden;">
            <div style="padding:4px 8px; background:#f5f7fa; font-size:12px; color:#909399;">原始代码</div>
            <div id="original-editor" style="height:calc(100% - 28px);"></div>
          </div>
          <div style="flex:1; border:1px solid #e4e7ed; border-radius:4px; overflow:hidden;">
            <div style="padding:4px 8px; background:#f0fdf4; font-size:12px; color:#22c55e;">注释后代码</div>
            <div id="modified-editor" style="height:calc(100% - 28px);"></div>
          </div>
        </div>
      `

      const origEl = editorContainer.value.querySelector('#original-editor')
      const modEl = editorContainer.value.querySelector('#modified-editor')

      const origEditor = monaco.editor.create(origEl, {
        value: props.original,
        language: lang,
        theme: 'vs-light',
        readOnly: true,
        minimap: { enabled: false },
        fontSize: 14,
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
      })

      const modEditor = monaco.editor.create(modEl, {
        value: props.modified,
        language: lang,
        theme: 'vs-light',
        readOnly: true,
        minimap: { enabled: false },
        fontSize: 14,
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
      })

      // 同步滚动
      origEditor.onDidScrollChange((e) => {
        modEditor.setScrollTop(e.scrollTop)
      })
      modEditor.onDidScrollChange((e) => {
        origEditor.setScrollTop(e.scrollTop)
      })

      editor = { dispose: () => { origEditor.dispose(); modEditor.dispose() } }
    }

    // 监听变化
    watch(
      () => [props.original, props.modified, props.viewMode, props.language],
      () => {
        nextTick(() => initEditor())
      }
    )

    onMounted(() => {
      nextTick(() => initEditor())
    })

    onBeforeUnmount(() => {
      if (editor) editor.dispose()
    })

    return { editorContainer }
  },
}
</script>

<style scoped>
.monaco-diff-viewer {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}
.editor-container {
  width: 100%;
  min-height: 400px;
}
</style>
