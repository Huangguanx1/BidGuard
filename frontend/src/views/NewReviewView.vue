<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, createReview, uploadDocument, type DocumentSummary } from '../api'

type Role = 'tender' | 'bid'

const files = ref<Record<Role, File | null>>({ tender: null, bid: null })
const results = ref<Partial<Record<Role, DocumentSummary>>>({})
const uploading = ref(false)
const reviewing = ref(false)
const router = useRouter()
const consent = ref(false)
const provider = ref('openai_compatible')
onMounted(async () => { try { provider.value = (await api<{model_provider: string}>('/health')).model_provider } catch {} })
const canUpload = computed(() => files.value.tender && files.value.bid && !uploading.value)
const canReview = computed(() => results.value.tender && results.value.bid && !reviewing.value && !uploading.value && (provider.value === 'ollama' || consent.value))

function chooseFile(role: Role, event: Event) {
  const input = event.target as HTMLInputElement
  files.value[role] = input.files?.[0] ?? null
  delete results.value[role]
}

async function startReview() {
  if (!results.value.tender || !results.value.bid) return
  reviewing.value = true
  try {
    const review = await createReview(results.value.tender.id, results.value.bid.id, consent.value)
    await router.push(`/reviews/${review.id}`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'AI 审查失败')
  } finally {
    reviewing.value = false
  }
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
  <section class="page review-page">
    <header class="page-title">
      <div class="page-title-row">
        <div>

          <h1>上传并解析文件</h1>
        </div>
        <el-tag type="info" effect="plain">文件在本机解析</el-tag>
      </div>
      <p>先上传一份招标文件和一份投标文件，系统会识别结构并准备后续匹配。</p>
    </header>

    <ol class="upload-progress" aria-label="新建审查步骤">
      <li :class="{active: !results.tender || !results.bid}"><span>1</span>上传并解析</li>
      <li :class="{active: results.tender && results.bid}"><span>2</span>确认并开始审查</li>
      <li><span>3</span>进入人工复核</li>
    </ol>
    <div class="upload-grid">
      <el-card v-for="role in (['tender', 'bid'] as Role[])" :key="role" class="upload-card" :class="`upload-card--${role}`" shadow="never">
        <template #header>
          <div class="card-heading"><strong>{{ role === 'tender' ? '招标文件' : '投标文件' }}</strong><el-tag v-if="results[role]" type="success" effect="plain" size="small">解析完成</el-tag></div>
        </template>
        <label class="file-field dropzone">
          <span class="dropzone__badge" aria-hidden="true">{{ role === 'tender' ? '招' : '投' }}</span>
          <span class="dropzone__title">选择{{ role === 'tender' ? '招标' : '投标' }}文件</span>
          <span class="dropzone__hint">点击选择文件 · DOCX / 文本型 PDF</span>
          <input :aria-label="role === 'tender' ? '选择招标文件' : '选择投标文件'" :disabled="uploading || reviewing" accept=".docx,.pdf" type="file" @change="chooseFile(role, $event)" />
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

    <el-alert v-if="provider !== 'ollama'" title="AI 审查将把候选文档片段发送给你配置的外部模型服务。请确认有权发送这些文件。" type="warning" :closable="false" show-icon />
    <el-checkbox v-if="provider !== 'ollama'" v-model="consent">我已了解并同意发送候选文档片段</el-checkbox>
    <div class="actions">
      <el-button :type="results.tender && results.bid ? 'default' : 'primary'" size="large" :disabled="!canUpload" :loading="uploading" @click="parseFiles">
        上传并解析
      </el-button>
      <el-button :type="results.tender && results.bid ? 'primary' : 'default'" size="large" :disabled="!canReview" :loading="reviewing" @click="startReview">
        开始 AI 审查
      </el-button>
    </div>

  </section>
</template>
