<template>
  <section class="page narrow-page">
    <div>
      <p class="eyebrow">本地招投标文件审查</p>
      <h1>让每条风险都能回到原文</h1>
      <p class="lead">
        上传招标文件与投标文件，BidGuard AI 将通过确定性规则、受控模型工作流和人工复核生成可追溯结论。
      </p>
      <el-button type="primary" size="large" tag="router-link" to="/reviews/new">
        新建审查
      </el-button>
    </div>
    <el-alert
      title="第一阶段已开放文件解析；AI 审查工作流将在下一阶段接入。"
      type="info"
      :closable="false"
      show-icon
    />
  </section>
</template>

