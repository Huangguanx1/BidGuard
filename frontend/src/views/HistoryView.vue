<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listReviews, type ReviewHistoryItem } from '../api'

const items = ref<ReviewHistoryItem[]>([])
const loading = ref(true)

const statusLabels = {
  awaiting_review: '待复核',
  running: '执行中',
  failed: '失败',
}

function statusType(status: ReviewHistoryItem['status']) {
  if (status === 'awaiting_review') return 'success'
  if (status === 'running') return 'warning'
  return 'danger'
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

async function loadHistory() {
  loading.value = true
  try {
    items.value = (await listReviews()).items
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '获取审查历史失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadHistory)
</script>

<template>
  <section class="page history-page">
    <header class="page-title">
      <div class="page-title-row">
        <div>
          <p class="eyebrow">本地审查记录</p>
          <h1>审查历史</h1>
        </div>
        <el-button type="primary" tag="router-link" to="/reviews/new">新建审查</el-button>
      </div>
      <p>所有记录保存在本机 SQLite 中，方便回看每次审查的文件、风险数量和模型信息。</p>
    </header>

    <el-card class="history-card results-card" shadow="never" v-loading="loading">
      <el-empty v-if="!loading && !items.length" description="还没有审查记录">
        <el-button type="primary" tag="router-link" to="/reviews/new">开始第一次审查</el-button>
      </el-empty>
      <el-table v-else-if="!loading" :data="items" stripe>
        <el-table-column label="审查记录" min-width="280">
          <template #default="scope">
            <div class="history-name">{{ scope.row.name }}</div>
            <div class="history-files">{{ scope.row.tender_file_name }} <span>↔</span> {{ scope.row.bid_file_name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope"><el-tag :type="statusType(scope.row.status as ReviewHistoryItem['status'])" effect="light">{{ statusLabels[scope.row.status as ReviewHistoryItem['status']] }}</el-tag></template>
        </el-table-column>
        <el-table-column label="风险" width="110">
          <template #default="scope"><span class="risk-count" :class="{ 'risk-count--active': scope.row.high_risk_count }">{{ scope.row.finding_count }} <small>项</small></span><small v-if="scope.row.high_risk_count">{{ scope.row.high_risk_count }} 项高风险</small></template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型" min-width="150" />
        <el-table-column label="创建时间" width="180">
          <template #default="scope">{{ formatDate(scope.row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>
