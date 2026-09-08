<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from './api'
const configured = ref(false)
const checking = ref(false)
onMounted(async () => { try { configured.value = (await api<{model_configured: boolean}>('/health')).model_configured } catch {} })
async function checkModel() { checking.value = true; try { await api('/model/check', 'POST'); configured.value = true; ElMessage.success('模型连接正常') } catch (e) { ElMessage.error(e instanceof Error ? e.message : '连接失败') } finally { checking.value = false } }
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand-lockup">
        <RouterLink to="/" class="brand-mark" aria-label="BidGuard 首页"><svg viewBox="0 0 32 36" fill="none" aria-hidden="true"><path d="M16 2 29 7v12c0 7-7 12-13 15C10 31 3 26 3 19V7L16 2Z" stroke="currentColor" stroke-width="2"/><path d="m10 17 4 4 9-10" stroke="currentColor" stroke-width="2.5"/></svg></RouterLink>
        <div>
          <RouterLink class="brand" to="/">BidGuard AI</RouterLink>
          <span class="brand-subtitle">招投标文件审阅工作区</span>
        </div>
      </div>
      <nav aria-label="主导航">
        <RouterLink to="/">工作区</RouterLink>
        <RouterLink to="/reviews">审查历史</RouterLink>
        <RouterLink to="/evals">质量评测</RouterLink>
        <RouterLink class="nav-primary" to="/reviews/new">新建审查</RouterLink>
      </nav>
      <el-button class="connection-button" link :loading="checking" @click="checkModel"><span class="connection-dot" :class="{configured}" />{{ configured ? '测试模型连接' : '模型未配置' }}</el-button>
    </el-header>
    <el-main>
      <RouterView :key="$route.fullPath" />
    </el-main>
    <footer class="app-footer"><span>BidGuard AI</span><span>文件保存在本机，AI 审查使用配置的模型服务。</span><RouterLink to="/workflow">了解审查流程</RouterLink></footer>
  </el-container>
</template>
