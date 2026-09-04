<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createReview, uploadDocument, type DocumentSummary, type ReviewRun } from '../api'

type Role = 'tender' | 'bid'

const files = ref<Record<Role, File | null>>({ tender: null, bid: null })
const results = ref<Partial<Record<Role, DocumentSummary>>>({})
const uploading = ref(false)
const reviewing = ref(false)
const review = ref<ReviewRun | null>(null)
const canUpload = computed(() => files.value.tender && files.value.bid && !uploading.value)
const canReview = computed(() => results.value.tender && results.value.bid && !reviewing.value)

const categoryLabels = {
  qualification: '资格条件',
  disqualification: '废标条款',
  scoring: '评分标准',
  timeline: '时间节点',
  materials: '材料要求',
}
const statusLabels = {
  satisfied: '满足',
  partial: '部分满足',
  not_satisfied: '不满足',
  not_found: '未找到',
  uncertain: '待确认',
}
const findingCategoryLabels = {
  amount: '金额',
  date: '日期',
  project_name: '项目名称',
  duration: '工期',
}

function checkFor(requirementId: string) {
  return review.value?.requirement_checks.find((item) => item.requirement_id === requirementId)
}

function statusType(status: keyof typeof statusLabels) {
  if (status === 'satisfied') return 'success'
  if (status === 'partial' || status === 'uncertain') return 'warning'
  return 'danger'
}

function chooseFile(role: Role, event: Event) {
  const input = event.target as HTMLInputElement
  files.value[role] = input.files?.[0] ?? null
  delete results.value[role]
  review.value = null
}

async function startReview() {
  if (!results.value.tender || !results.value.bid) return
  reviewing.value = true
  try {
    review.value = await createReview(results.value.tender.id, results.value.bid.id)
    ElMessage.success(`已完成 ${review.value.requirements.length} 条要求匹配`)
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
      <el-button size="large" :disabled="!canReview" :loading="reviewing" @click="startReview">
        开始 AI 审查
      </el-button>
    </div>

    <el-card v-if="review" class="requirements" shadow="never">
      <template #header>
        <strong>招标要求（{{ review.requirements.length }}）</strong>
        <span>模型：{{ review.model_name }} · Token：{{ review.input_tokens + review.output_tokens }}</span>
      </template>
      <el-table :data="review.requirements" stripe>
        <el-table-column label="类别" width="110">
          <template #default="scope">{{ categoryLabels[scope.row.category as keyof typeof categoryLabels] }}</template>
        </el-table-column>
        <el-table-column prop="title" label="要求" min-width="150" />
        <el-table-column prop="description" label="说明" min-width="260" />
        <el-table-column label="强制" width="80">
          <template #default="scope">{{ scope.row.mandatory ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column label="置信度" width="90">
          <template #default="scope">{{ Math.round(scope.row.confidence * 100) }}%</template>
        </el-table-column>
        <el-table-column label="匹配" width="110">
          <template #default="scope">
            <el-tag :type="statusType(checkFor(scope.row.id)!.match_status)">
              {{ statusLabels[checkFor(scope.row.id)!.match_status] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="判断理由" min-width="260">
          <template #default="scope">{{ checkFor(scope.row.id)?.reason }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="review" class="requirements" shadow="never">
      <template #header>
        <strong>确定性矛盾（{{ review.findings.length }}）</strong>
        <span>金额 · 日期 · 项目名称 · 工期</span>
      </template>
      <el-empty v-if="!review.findings.length" description="未发现明确矛盾" />
      <el-table v-else :data="review.findings" stripe>
        <el-table-column label="风险" width="80">
          <template #default="scope"><el-tag type="danger">{{ scope.row.risk_level === 'high' ? '高' : '中' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="类别" width="100">
          <template #default="scope">{{ findingCategoryLabels[scope.row.category as keyof typeof findingCategoryLabels] }}</template>
        </el-table-column>
        <el-table-column prop="title" label="问题" min-width="170" />
        <el-table-column prop="description" label="说明" min-width="280" />
        <el-table-column prop="suggestion" label="整改建议" min-width="280" />
        <el-table-column label="置信度" width="90">
          <template #default="scope">{{ Math.round(scope.row.confidence * 100) }}%</template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>
