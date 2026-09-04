<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadDocument, type DocumentSummary } from '../api'

type Role = 'tender' | 'bid'

const files = ref<Record<Role, File | null>>({ tender: null, bid: null })
const results = ref<Partial<Record<Role, DocumentSummary>>>({})
const uploading = ref(false)
const canUpload = computed(() => files.value.tender && files.value.bid && !uploading.value)

function chooseFile(role: Role, event: Event) {
  const input = event.target as HTMLInputElement
  files.value[role] = input.files?.[0] ?? null
  delete results.value[role]
}

async function parseFiles() {
  if (!files.value.tender || !files.value.bid) return
  uploading.value = true
  try {
    results.value.tender = await uploadDocument(files.value.tender)
    results.value.bid = await uploadDocument(files.value.bid)
    ElMessage.success('两份文件解析完成')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '解析失败')
  } finally {
    uploading.value = false
  }
}

function formatBytes(bytes: number) {
  return `${(bytes / 1024).toFixed(1)} KB`
}
</script>

<template>
  <section class="page">
    <header class="page-title">
      <p class="eyebrow">第一步</p>
      <h1>上传并解析文件</h1>
      <p>仅支持 DOCX 和文本型 PDF，单个文件不超过 20 MB。</p>
    </header>

    <div class="upload-grid">
      <el-card v-for="role in (['tender', 'bid'] as Role[])" :key="role" shadow="never">
        <template #header>
          <strong>{{ role === 'tender' ? '招标文件' : '投标文件' }}</strong>
        </template>
        <label class="file-field">
          <span>选择 DOCX 或 PDF</span>
          <input accept=".docx,.pdf" type="file" @change="chooseFile(role, $event)" />
        </label>
        <p v-if="files[role]" class="selected-file">{{ files[role]?.name }}</p>

        <dl v-if="results[role]" class="summary-grid">
          <div><dt>大小</dt><dd>{{ formatBytes(results[role]!.file_size) }}</dd></div>
          <div><dt>页数</dt><dd>{{ results[role]!.page_count }}</dd></div>
          <div><dt>标题</dt><dd>{{ results[role]!.heading_count }}</dd></div>
          <div><dt>段落</dt><dd>{{ results[role]!.paragraph_count }}</dd></div>
          <div><dt>表格</dt><dd>{{ results[role]!.table_count }}</dd></div>
          <div><dt>字符</dt><dd>{{ results[role]!.text_char_count }}</dd></div>
        </dl>
        <el-alert
          v-for="warning in results[role]?.warnings"
          :key="warning"
          :title="warning"
          type="warning"
          :closable="false"
          show-icon
        />
      </el-card>
    </div>

    <div class="actions">
      <el-button type="primary" size="large" :disabled="!canUpload" :loading="uploading" @click="parseFiles">
        上传并解析
      </el-button>
      <el-button size="large" disabled>开始 AI 审查（第二阶段）</el-button>
    </div>
  </section>
</template>

