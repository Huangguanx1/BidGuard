<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, categoryLabels, statusLabels, matchLabels, reviewLabels, riskLabels, type ReviewRun, type Finding, type Evidence } from '../api'

const route = useRoute()
const review = ref<ReviewRun | null>(null)
const error = ref('')
const busy = ref(false)
const risk = ref('')
const category = ref('')
const disposition = ref('pending')
const tab = ref('findings')
const editing = ref<Finding | null>(null)
const dialog = ref(false)
const form = ref({ title: '', description: '', risk_level: 'medium' as Finding['risk_level'], suggestion: '', reviewer_note: '' })
const evidenceDialog = ref(false)
const evidenceText = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
let alive = true
const stageLabels: Record<string, string> = { queued: '等待执行', validating_documents: '检查文档', extracting_requirements: '提取招标要求', requirements_extracted: '要求提取完成', matching_responses: '逐项匹配投标响应', requirements_matched: '匹配完成', checking_evidence: '检查矛盾与原文证据', evidence_validated: '证据检查完成', human_review: '等待人工复核', consistency_checked: '等待人工复核', completed: '审查已完成' }
const pending = computed(() => review.value?.findings.filter(f => f.review_status === 'pending').length ?? 0)
const editable = computed(() => review.value?.status === 'awaiting_review')
const filtered = computed(() => review.value?.findings.filter(f => (!risk.value || effective(f).risk_level === risk.value) && (!category.value || f.category === category.value) && (!disposition.value || f.review_status === disposition.value)) ?? [])
const categories = computed(() => [...new Set(review.value?.findings.map(f => f.category) ?? [])])
const highCount = computed(() => review.value?.findings.filter(f => f.review_status !== 'ignored' && effective(f).risk_level === 'high').length ?? 0)
function effective(f: Finding) { return f.override || f }
function message(e: unknown) { return e instanceof Error ? e.message : '操作失败' }
function readableText(text: string) {
  try {
    const rows = JSON.parse(text)
    if (Array.isArray(rows) && rows.every(Array.isArray)) return rows.map(row => row.join(' | ')).join('\n')
  } catch { /* Ordinary paragraph text stays unchanged. */ }
  return text
}

async function load() {
  try {
    review.value = await api<ReviewRun>(`/reviews/${route.params.id}`)
    error.value = ''
    if (review.value.status === 'completed') disposition.value = ''
  } catch (e) { error.value = message(e) }
  if (alive && (!review.value || ['queued', 'running'].includes(review.value.status))) timer = setTimeout(load, 2000)
}
async function update(finding: Finding, status: Finding['review_status'], override?: Finding['override'], note = '') {
  busy.value = true
  try {
    review.value = await api<ReviewRun>(`/findings/${finding.id}`, 'PATCH', { review_status: status, reviewer_note: note, override: override ?? null })
    dialog.value = false
    ElMessage.success('复核结果已保存')
  } catch (e) { ElMessage.error(message(e)) } finally { busy.value = false }
}
function edit(f: Finding) {
  editing.value = f
  const current = effective(f)
  form.value = { title: current.title, description: current.description, risk_level: current.risk_level, suggestion: current.suggestion, reviewer_note: f.reviewer_note || '' }
  dialog.value = true
}
async function saveEdit() {
  if (!editing.value) return
  const { reviewer_note, ...override } = form.value
  if (![override.title, override.description, override.suggestion].every(v => v.trim())) { ElMessage.warning('请填写标题、说明和建议'); return }
  await update(editing.value, 'modified', override, reviewer_note)
}
async function finalize() {
  try {
    await ElMessageBox.confirm('完成后将冻结所有复核结论，之后可下载报告。是否完成？', '完成复核', { confirmButtonText: '完成并冻结', cancelButtonText: '继续复核' })
    busy.value = true
    review.value = await api<ReviewRun>(`/reviews/${route.params.id}/finalize`, 'POST')
    disposition.value = ''
    ElMessage.success('已完成，可下载报告')
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(message(e)) } finally { busy.value = false }
}
async function retry() {
  busy.value = true
  try { review.value = await api<ReviewRun>(`/reviews/${route.params.id}/retry`, 'POST'); await load() }
  catch (e) { ElMessage.error(message(e)) } finally { busy.value = false }
}
async function showEvidence(e: Evidence) {
  if (!review.value) return
  const doc = e.document_role === 'tender' ? review.value.tender_document_id : review.value.bid_document_id
  try {
    const block = await api<{content: string; page_number: number; location_confidence: number}>(`/documents/${doc}/blocks/${e.block_id}`)
    evidenceText.value = `${e.document_role === 'tender' ? '招标' : '投标'}文件 第 ${block.page_number ?? '未知'} 页\n\n${readableText(block.content)}`
    evidenceDialog.value = true
  } catch (err) { ElMessage.error(message(err)) }
}
onMounted(load)
onUnmounted(() => { alive = false; if (timer) clearTimeout(timer) })
</script>

<template>
  <section class="page workbench">
    <el-alert v-if="error" :title="error" type="error" :closable="false"><el-button @click="load">重新加载</el-button></el-alert>
    <template v-if="review">
      <header class="page-title">
        <p class="eyebrow"><RouterLink to="/reviews">审查历史</RouterLink> / 审查工作台</p>
        <div class="page-title-row"><h1>{{ review.name }}</h1><el-tag>{{ statusLabels[review.status] }}</el-tag></div>
        <p>逐项查看原文依据，确认需要处理的问题。</p><details class="run-metadata"><summary>本次审查信息</summary><p>模型 {{ review.model_name }} · 第 {{ review.run_attempt }} 次执行 · Token {{ review.input_tokens + review.output_tokens }}</p></details>
      </header>
      <el-card v-if="['queued', 'running'].includes(review.status)" shadow="never">
        <p>{{ stageLabels[review.current_stage] || review.current_stage }}。可以离开页面，稍后从历史记录继续查看。</p>
        <el-progress :percentage="review.progress" />
      </el-card>
      <el-alert v-if="review.status === 'failed'" :title="review.error_message || '审查失败'" type="error" :closable="false"><el-button :loading="busy" @click="retry">从检查点重试</el-button></el-alert>
      <div class="review-stats">
        <el-card shadow="never"><strong>{{ review.requirements.length }}</strong><span>招标要求</span></el-card>
        <el-card shadow="never"><strong>{{ review.findings.length }}</strong><span>发现问题</span></el-card>
        <el-card shadow="never"><strong>{{ highCount }}</strong><span>保留的高风险</span></el-card>
        <el-card shadow="never"><strong>{{ pending }}</strong><span>待人工确认</span></el-card>
      </div>
      <div class="actions review-toolbar">
        <span v-if="editable" class="review-toolbar__hint">{{ pending ? `还有 ${pending} 项待确认，处理后可生成报告` : '所有问题已处理，可以生成报告' }}</span>
        <el-button v-if="editable" type="primary" :disabled="pending > 0" :loading="busy" @click="finalize">完成复核并生成报告</el-button>
        <template v-if="review.status === 'completed'">
          <el-button type="primary" tag="a" :href="`/api/reviews/${review.id}/report?format=docx`">下载 Word 报告</el-button>
          <el-button tag="a" :href="`/api/reviews/${review.id}/report?format=json`">下载 JSON</el-button>
          <span>报告基于已冻结的人工复核结果</span>
        </template>
        <el-button tag="router-link" to="/reviews">返回历史</el-button>
      </div>
      <el-tabs v-model="tab">
        <el-tab-pane label="风险与人工复核" name="findings">
          <div class="filter-row">
            <el-select aria-label="风险等级" v-model="risk" clearable placeholder="所有风险"><el-option v-for="(label, key) in riskLabels" :key="key" :label="label + '风险'" :value="key" /></el-select>
            <el-select aria-label="问题类别" v-model="category" clearable placeholder="所有类别"><el-option v-for="key in categories" :key="key" :label="categoryLabels[key]" :value="key" /></el-select>
            <el-select aria-label="复核状态" v-model="disposition" clearable placeholder="所有状态"><el-option v-for="(label, key) in reviewLabels" :key="key" :label="label" :value="key" /></el-select>
          </div>
          <span class="filter-count">显示 {{ filtered.length }} / {{ review.findings.length }} 项</span>
          <el-empty v-if="!filtered.length" description="当前筛选下没有问题"><el-button v-if="review.findings.length" @click="risk = ''; category = ''; disposition = ''">查看全部问题</el-button></el-empty>
          <el-card v-for="f in filtered" :key="f.id" :data-risk="effective(f).risk_level" class="finding-card" shadow="never">
            <template #header><div class="card-heading"><strong>{{ effective(f).title }}</strong><span><el-tag :type="effective(f).risk_level === 'high' ? 'danger' : effective(f).risk_level === 'medium' ? 'warning' : 'info'">{{ riskLabels[effective(f).risk_level] }}风险</el-tag> <el-tag type="info">{{ reviewLabels[f.review_status] }}</el-tag></span></div></template>
            <p class="muted">{{ categoryLabels[f.category] }} · {{ f.type === 'consistency' ? '规则置信度' : 'AI 置信度' }} {{ Math.round(f.confidence * 100) }}%</p>
            <p>{{ effective(f).description }}</p><p><b>建议：</b>{{ effective(f).suggestion }}</p>
            <p v-if="f.reviewer_note"><b>人工备注：</b>{{ f.reviewer_note }}</p>
            <details v-if="f.override"><summary>查看原始结论</summary><p>{{ f.title }}：{{ f.description }}</p></details>
            <div class="evidence-grid"><blockquote v-for="e in f.evidence" :key="e.block_id" :data-role="e.document_role"><el-button link type="primary" @click="showEvidence(e)">{{ e.document_role === 'tender' ? '招标' : '投标' }} · 第 {{ e.page_number ?? '未知' }} 页 · 查看原文</el-button><el-tag v-if="e.location_confidence < .9" type="warning">页码需核对</el-tag><p>{{ readableText(e.excerpt) }}</p></blockquote></div>
            <div v-if="editable" class="actions"><el-button type="success" :disabled="busy" @click="update(f, 'confirmed')">确认问题</el-button><el-button :disabled="busy" @click="update(f, 'ignored')">忽略</el-button><el-button :disabled="busy" @click="edit(f)">修改结论</el-button><el-button v-if="f.review_status !== 'pending'" link :disabled="busy" @click="update(f, 'pending')">恢复待确认</el-button></div>
          </el-card>
        </el-tab-pane>
        <el-tab-pane label="完整逐项匹配" name="requirements">
          <el-card v-for="r in review.requirements" :key="r.id" class="finding-card" shadow="never"><h3>{{ r.title }} <el-tag type="info">{{ categoryLabels[r.category] }}</el-tag></h3><p>{{ r.description }}</p>
            <template v-for="c in review.requirement_checks.filter(c => c.requirement_id === r.id)" :key="c.id"><el-tag :type="c.match_status === 'satisfied' ? 'success' : 'warning'">{{ matchLabels[c.match_status] }}</el-tag><p>{{ c.reason }}</p><div class="evidence-grid"><blockquote v-for="e in [...c.tender_evidence, ...c.bid_evidence]" :key="e.block_id" :data-role="e.document_role"><el-button link type="primary" @click="showEvidence(e)">{{ e.document_role === 'tender' ? '招标' : '投标' }} · 第 {{ e.page_number }} 页 · 原文</el-button><p>{{ readableText(e.excerpt) }}</p></blockquote></div><details><summary>本项检查过的 {{ c.searched_block_ids.length }} 个投标块</summary><el-button v-for="id in c.searched_block_ids" :key="id" link type="primary" @click="showEvidence({block_id: id, document_role: 'bid', page_number: null, excerpt: '', location_confidence: 1})">{{ id }}</el-button></details></template>
          </el-card>
        </el-tab-pane>
      </el-tabs>
      <p class="muted">审查结论仅供辅助参考，请结合原始文件和专业判断使用。</p>
    </template>
    <el-dialog v-model="dialog" title="修改结论" width="min(640px, 94vw)"><el-form label-position="top"><el-form-item label="标题"><el-input v-model="form.title" maxlength="100" /></el-form-item><el-form-item label="风险等级"><el-select v-model="form.risk_level"><el-option v-for="(label,key) in riskLabels" :key="key" :label="label" :value="key" /></el-select></el-form-item><el-form-item label="问题说明"><el-input v-model="form.description" type="textarea" :rows="4" maxlength="2000" /></el-form-item><el-form-item label="整改建议"><el-input v-model="form.suggestion" type="textarea" :rows="3" maxlength="2000" /></el-form-item><el-form-item label="人工备注"><el-input v-model="form.reviewer_note" type="textarea" maxlength="2000" /></el-form-item></el-form><template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="saveEdit">保存修改</el-button></template></el-dialog>
    <el-dialog v-model="evidenceDialog" title="原文证据" width="min(800px, 94vw)"><pre class="evidence-text">{{ evidenceText }}</pre></el-dialog>
  </section>
</template>
