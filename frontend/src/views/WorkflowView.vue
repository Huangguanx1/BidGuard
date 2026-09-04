<template>
  <section class="page workflow-page">
    <header class="page-title">
      <p class="eyebrow">审查流程</p>
      <h1>从文件到结论，过程清晰可追溯</h1>
      <p>BidGuard AI 将确定性规则和模型能力放在同一条可解释的审查链路中，先保留证据，再输出结论。</p>
    </header>

    <div class="workflow-timeline">
      <article class="workflow-step"><span>01</span><div><h2>上传与解析</h2><p>上传 DOCX 或文本型 PDF，识别标题、段落、表格和页码，建立可检索的文档块。</p><el-tag effect="plain">确定性处理</el-tag></div></article>
      <article class="workflow-step"><span>02</span><div><h2>提取招标要求</h2><p>从资格条件、废标条款、评分标准、时间节点和材料要求中整理结构化要求，并保留原文证据。</p><el-tag type="warning" effect="plain">模型节点</el-tag></div></article>
      <article class="workflow-step"><span>03</span><div><h2>逐项匹配与矛盾检查</h2><p>将投标响应与招标要求逐项对照，同时检查金额、日期、项目名称和工期是否前后一致。</p><el-tag type="success" effect="plain">规则 + 模型</el-tag></div></article>
      <article class="workflow-step"><span>04</span><div><h2>输出风险结果</h2><p>按风险等级展示问题说明、原文证据、整改建议和置信度，并保存为本地审查记录。</p><el-tag type="info" effect="plain">可追溯结果</el-tag></div></article>
    </div>

    <div class="workflow-footer"><span>准备开始？</span><el-button type="primary" tag="router-link" to="/reviews/new">上传文件开始审查</el-button></div>
  </section>
</template>
