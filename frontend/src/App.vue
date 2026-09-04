<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand-lockup">
        <span class="brand-mark">B</span>
        <div>
          <RouterLink class="brand" to="/">BidGuard AI</RouterLink>
          <span class="brand-subtitle">智能招投标审查</span>
        </div>
      </div>
      <nav aria-label="主导航">
        <RouterLink to="/">审查历史</RouterLink>
        <RouterLink class="nav-primary" to="/reviews/new">新建审查</RouterLink>
      </nav>
    </el-header>
    <el-main>
      <RouterView />
    </el-main>
  </el-container>
</template>
