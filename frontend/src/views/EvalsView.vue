<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
interface Run { id: string; status: string; created_at: string; with_model: boolean; model_name: string | null; duration_ms?: number; input_tokens?: number; output_tokens?: number; error?: string; limitations?: string; metrics?: Record<string, number | null>; results: { case_id: string; passed: boolean; error: string | null; expected_consistency: string[]; actual_consistency: string[]; matching: {category: string; expected: string; actual: string}[]; severe_misses: unknown[] }[] }
const runs = ref<Run[]>([])
const selected = ref('')
const withModel = ref(false)
const consent = ref(false)
const busy = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let alive = true
const names: Record<string, string> = { case_pass_rate: '案例通过率', consistency_precision: '一致性精确率', consistency_recall: '一致性召回率', requirement_recall: '标注要求召回率', matching_macro_f1: '匹配 Macro-F1', structured_output_success: '结构化输出成功率', evidence_block_validity: '证据块有效率', severe_misses: '严重漏检数', page_accuracy: '页码准确率' }
async function load() { try { runs.value = (await api<{items: Run[]}>('/eval-runs')).items; if (!selected.value) selected.value = runs.value[0]?.id || '' } catch (e) { ElMessage.error(e instanceof Error ? e.message : '评测加载失败') }; if (alive) timer = setTimeout(load, 5000) }
async function start() { busy.value = true; try { const run = await api<Run>('/eval-runs', 'POST', { with_model: withModel.value, external_processing_consent: consent.value }); selected.value = run.id; runs.value.unshift(run) } catch (e) { ElMessage.error(e instanceof Error ? e.message : '评测启动失败') } finally { busy.value = false } }
onMounted(load)
onUnmounted(() => { alive = false; if (timer) clearTimeout(timer) })
</script>
<template>
  <section class="page evals-page"><header class="page-title"><h1>评测记录</h1><p>六组固定案例覆盖五类要求和四类一致性检查。结果用于发现问题，小样本得分不代表真实业务准确率。</p></header>
    <el-card shadow="never"><el-checkbox v-model="withModel">同时评测模型提取与匹配</el-checkbox><div v-if="withModel"><el-alert title="将发送仓库内的虚构样本给配置的模型服务，可能产生 API 费用。" type="warning" :closable="false" /><el-checkbox v-model="consent">同意调用模型评测虚构样本</el-checkbox></div><el-button type="primary" :loading="busy" :disabled="runs.some(r => r.status === 'running') || (withModel && !consent)" @click="start">运行评测</el-button></el-card>
    <div class="filter-row"><el-select v-model="selected" placeholder="选择评测记录" style="width:100%"><el-option v-for="run in runs" :key="run.id" :value="run.id" :label="`${new Date(run.created_at).toLocaleString()} · ${run.with_model ? run.model_name : '规则评测'} · ${run.status}`" /></el-select></div>
    <template v-for="run in runs.filter(r => r.id === selected)" :key="run.id"><el-alert v-if="run.error" :title="run.error" type="error" :closable="false" /><p>{{ run.status === 'running' ? '执行中' : run.status === 'completed' ? '执行结束' : '执行失败' }} · 已处理 {{ run.results.length }}/6 个案例 · Token {{ (run.input_tokens || 0) + (run.output_tokens || 0) }}</p>
      <div v-if="run.metrics" class="review-stats"><el-card v-for="(value,key) in run.metrics" :key="key" shadow="never"><strong>{{ value === null ? '未评测' : key === 'severe_misses' ? value : `${(value * 100).toFixed(1)}%` }}</strong><span>{{ names[key] || key }}</span></el-card></div>
      <el-card v-for="item in run.results" :key="item.case_id" class="finding-card" shadow="never"><h3>{{ item.case_id }} <el-tag :type="item.passed ? 'success' : 'danger'">{{ item.passed ? '通过' : '未通过' }}</el-tag></h3><p v-if="item.error">{{ item.error }}</p><p>预期矛盾：{{ item.expected_consistency.join('、') || '无' }}；实际：{{ item.actual_consistency.join('、') || '无' }}</p><p v-for="(m,i) in item.matching" :key="i">{{ m.category }}：预期 {{ m.expected }}，实际 {{ m.actual }}</p><el-alert v-if="item.severe_misses.length" :title="`严重漏检 ${item.severe_misses.length} 项`" type="error" :closable="false" /></el-card><p class="muted">{{ run.limitations }}</p>
    </template><el-empty v-if="!runs.length" description="尚未运行评测" />
  </section>
</template>
