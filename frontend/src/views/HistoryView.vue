<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listReviews, type ReviewHistoryItem } from '../api'

const items = ref<ReviewHistoryItem[]>([])
const loading = ref(true)
const page = ref(1)
const total = ref(0)

const statusLabels = {
  awaiting_review: '待复核',
  running: '执行中',
  failed: '失败',
  queued: '排队中',
  completed: '已完成',
}

function statusType(status: ReviewHistoryItem['status']) {
  if (status === 'awaiting_review' || status === 'completed') return 'success'
  if (status === 'running' || status === 'queued') return 'warning'
  return 'danger'
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

async function loadHistory() {
  loading.value = true
  try {
    const response = await listReviews((page.value - 1) * 20)
    items.value = response.items
    total.value = response.total
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

          <h1>审查历史</h1>
        </div>
        <el-button type="primary" tag="router-link" to="/reviews/new">新建审查</el-button>
      </div>
      <p>查看已完成的报告，或继续处理尚未复核的问题。</p>
    </header>

    <div class="section-heading"><span class="muted">共 {{ total }} 份审查记录</span><el-button :loading="loading" @click="loadHistory">刷新记录</el-button></div>
    <el-card class="history-card results-card" shadow="never" v-loading="loading">
      <el-empty v-if="!loading && !items.length" description="还没有审查记录">
        <el-button type="primary" tag="router-link" to="/reviews/new">开始第一次审查</el-button>
      </el-empty>
      <el-table v-else-if="!loading" :data="items" stripe>
        <el-table-column label="审查记录" min-width="280">
          <template #default="scope">
            <router-link class="history-name" :to="`/reviews/${scope.row.id}`">{{ scope.row.name }}</router-link>
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
        <el-table-column label="操作" width="100"><template #default="scope"><el-button link type="primary" tag="router-link" :to="`/reviews/${scope.row.id}`">查看详情</el-button></template></el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="scope">{{ formatDate(scope.row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-pagination v-if="total > 20" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="loadHistory" />
  </section>
</template>
