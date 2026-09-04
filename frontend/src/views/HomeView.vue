<template>
  <section class="page home-page">
    <div class="hero-panel">
      <div class="hero-copy">
        <p class="eyebrow">本地招投标文件审查</p>
        <h1>让每条风险<br /><span>都回到原文</span></h1>
        <p class="lead">
          上传招标文件与投标文件，BidGuard AI 会提取招标要求、逐项匹配响应，并定位金额、日期、项目名称和工期矛盾。
        </p>
        <div class="hero-actions">
          <el-button type="primary" size="large" tag="router-link" to="/reviews/new">新建审查</el-button>
          <el-button size="large" plain tag="router-link" to="/reviews/new">查看流程</el-button>
        </div>
      </div>

      <div class="hero-visual" aria-label="审查摘要预览">
        <div class="preview-card">
          <div class="preview-card__top"><span class="status-dot"></span><span>审查摘要</span><span class="preview-label">本地工作区</span></div>
          <div class="preview-score"><strong>4</strong><span>项确定性风险</span></div>
          <div class="preview-bars">
            <div><span>金额</span><b style="width: 90%"></b></div>
            <div><span>日期</span><b style="width: 64%"></b></div>
            <div><span>工期</span><b style="width: 78%"></b></div>
          </div>
          <div class="preview-footer"><span>证据可追溯</span><span>置信度 92%</span></div>
        </div>
      </div>
    </div>

    <div class="capability-grid">
      <article class="capability-card"><span class="capability-icon">01</span><div><h3>结构化解析</h3><p>识别标题、段落、表格与页码</p></div></article>
      <article class="capability-card"><span class="capability-icon">02</span><div><h3>逐项匹配</h3><p>保留招标与投标侧证据块</p></div></article>
      <article class="capability-card"><span class="capability-icon">03</span><div><h3>矛盾定位</h3><p>金额、日期、项目名称、工期</p></div></article>
    </div>

    <div class="process-strip">
      <div class="section-kicker"><span>工作流</span><strong>三步得到可追溯结论</strong></div>
      <div class="process-steps">
        <div class="process-step"><b>01</b><span>上传文件</span><small>DOCX / 文本型 PDF</small></div>
        <div class="process-connector"></div>
        <div class="process-step"><b>02</b><span>提取与匹配</span><small>要求 · 响应 · 证据</small></div>
        <div class="process-connector"></div>
        <div class="process-step"><b>03</b><span>查看风险</span><small>问题 · 建议 · 置信度</small></div>
      </div>
    </div>
  </section>
</template>
