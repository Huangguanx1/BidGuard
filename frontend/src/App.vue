<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <RouterLink class="brand" to="/">BidGuard AI</RouterLink>
      <nav aria-label="主导航">
        <RouterLink to="/">审查历史</RouterLink>
        <RouterLink to="/reviews/new">新建审查</RouterLink>
      </nav>
    </el-header>
    <el-main>
      <RouterView />
    </el-main>
  </el-container>
</template>

