<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listReviews, statusLabels, type ReviewHistoryItem } from '../api'
const recent = ref<ReviewHistoryItem[]>([])
const loading = ref(true)
const error = ref('')
async function loadRecent() {
  loading.value = true
  try { recent.value = (await listReviews()).items.slice(0, 3); error.value = '' }
  catch { error.value = '暂时无法读取记录，请检查后端是否启动。' }
  finally { loading.value = false }
}
onMounted(loadRecent)
</script>

<template>
  <section class="page home-page">
    <div class="hero-panel">
      <div class="hero-copy">
        <h1>把要求逐项核清，<br>再交出投标文件。</h1>
        <p class="lead">让招标要求与投标响应并排呈现。找到缺项、核对矛盾，带着原文证据完成每一次复核。</p>
        <div class="hero-actions"><el-button type="primary" size="large" tag="router-link" to="/reviews/new">新建文件审查</el-button><RouterLink class="text-link" to="/reviews">继续已有审查</RouterLink></div>
        <p class="format-note">支持 DOCX 与文本型 PDF <span>人工复核后导出报告</span></p>
      </div>
      <div class="document-preview" aria-label="虚构样本的工期对照示例">
        <div class="document-preview__heading"><strong>原文对照</strong><span>虚构样本示例</span></div>
        <div class="document-pair">
          <article class="sample-sheet"><div class="sheet-label">招标文件 <span>第 1 页</span></div><h2>工期要求</h2><p>项目建设工期<br><mark>不得超过 150 日历天。</mark></p><div class="sheet-lines" aria-hidden="true"><i /><i /><i /></div></article>
          <article class="sample-sheet sample-sheet--bid"><div class="sheet-label">投标文件 <span>第 1 页</span></div><h2>工期承诺</h2><p>承诺建设工期<br><mark>为 180 日历天。</mark></p><div class="sheet-lines" aria-hidden="true"><i /><i /><i /></div></article>
        </div>
        <div class="sample-verdict"><span class="risk-marker" aria-hidden="true">!</span><div><strong>工期承诺超出招标要求</strong><p>核对进度计划，并修正投标响应。</p></div><span class="sample-verdict__status">待复核</span></div>
      </div>
    </div>
    <ol class="process-steps" aria-label="审查步骤">
      <li><span>1</span><div><strong>上传文件</strong><p>选择招标与投标文件</p></div></li>
      <li><span>2</span><div><strong>自动核对</strong><p>提取要求，匹配响应</p></div></li>
      <li><span>3</span><div><strong>人工复核</strong><p>对照证据，处理问题</p></div></li>
      <li><span>4</span><div><strong>导出报告</strong><p>保留最终结论与依据</p></div></li>
    </ol>
    <section class="recent-section" aria-labelledby="recent-title">
      <div class="section-heading"><div><h2 id="recent-title">最近的审查</h2><p>从上次停下的地方继续。</p></div><RouterLink class="text-link" to="/reviews">查看全部记录</RouterLink></div>
      <p v-if="loading" class="empty-note" role="status">正在读取审查记录…</p>
      <div v-else-if="error" class="empty-note"><p>{{ error }}</p><el-button @click="loadRecent">重新加载</el-button></div>
      <div v-else-if="!recent.length" class="empty-note"><h3>准备好两份文件，就可以开始</h3><p>创建第一份审查后，你可以在这里继续复核或下载报告。</p><el-button tag="router-link" to="/reviews/new">创建第一份审查</el-button></div>
      <RouterLink v-for="item in recent" :key="item.id" class="recent-row" :to="`/reviews/${item.id}`"><span class="document-icon" aria-hidden="true">≡</span><div class="recent-row__name"><strong>{{ item.name }}</strong><span>{{ new Date(item.created_at).toLocaleDateString('zh-CN') }} · {{ item.model_name }}</span></div><el-tag :type="item.status === 'failed' ? 'danger' : item.status === 'completed' ? 'success' : 'info'" effect="plain">{{ statusLabels[item.status] }}</el-tag><span class="recent-row__action">打开审查</span></RouterLink>
    </section>
  </section>
</template>
