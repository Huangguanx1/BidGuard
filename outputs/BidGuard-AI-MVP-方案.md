# BidGuard AI MVP 方案

> 状态：待确认  
> 版本：v0.3  
> 日期：2026-09-04

## 0. 产品边界与关键决策

BidGuard AI 是本地运行的招投标文件智能审查助手。用户上传一份招标文件和一份投标文件，系统以“确定性解析与规则 + 受控 LLM 节点 + 人工复核”的固定流程提取要求、逐项核对、发现矛盾并生成可追溯报告。

目标用户：需要在提交前完成投标文件自查的投标专员、项目经理及法务/商务人员。

MVP 成功标准：对虚构或脱敏样本完成一次从上传、解析、审查、人工确认到报告导出的完整闭环；每条结论都能回到原文位置；评测结果可复现。

关键决策：

- 单机、单用户、本地运行；不做登录和权限系统。
- 同一次审查严格包含一份招标文件和一份投标文件。
- 仅支持 `.docx` 与文本型 `.pdf`，明确拒绝扫描 PDF。
- PDF 直接按页解析；DOCX 使用结构解析，并通过本机 LibreOffice 无界面转 PDF 后定位页码。转换不可用时上传失败并给出安装提示，避免生成不可信页码。
- 文件、SQLite 数据库和报告均保存在本地 `data/`；该目录加入 `.gitignore`。
- 开发和演示阶段优先使用用户自行申请的免费 OpenAI Compatible API，或使用本地 Ollama；仓库不绑定、代领或内置任何第三方密钥。免费额度和可用模型可能变化，不作为程序逻辑的一部分。
- 模型提供方通过 `.env` 配置 `base_url`、`api_key`、`model` 等参数，后续切换付费接口时不修改业务节点。API Key 不进入数据库、日志、前端或 Git。使用远程 API 时，开始审查前必须提示文档片段会发送给外部服务；只有 Ollama 模式可声明为完全本地处理。
- LLM 输出必须通过 Pydantic 校验；模型不得直接修改数据库或决定最终人工状态。
- 审查异步执行使用 FastAPI `BackgroundTasks`，不引入 Redis/Celery。进程意外退出后允许用户手动重试。
- 长文档不整篇发送给模型；使用标题路径、关键词规则、SQLite FTS5 和相邻块窗口筛选候选上下文，不引入向量数据库。

非目标：OCR、多租户、云部署、微服务、消息队列、向量数据库、通用聊天、多智能体角色扮演、复杂权限与协作审批。

---

## 1. 项目 PRD

### 1.1 用户问题

人工审阅招投标文件耗时，容易漏看废标条款、材料缺失和跨章节数据矛盾。通用聊天模型又容易缺少逐条覆盖、原文证据和稳定输出，无法直接形成可复核的工作记录。

### 1.2 产品价值

- 将招标要求结构化，降低漏项风险。
- 将每项要求与投标响应建立明确对应关系。
- 用确定性规则检查金额、日期、项目名称和工期等一致性。
- 保留原文证据、置信度与人工处置结果，便于复核。
- 固化样本、模型与提示词版本，展示工程质量而非一次性演示。

### 1.3 核心功能与验收口径

| 功能 | MVP 行为 | 不包含 |
|---|---|---|
| 文件上传 | 上传招标/投标 DOCX 或文本 PDF；校验扩展名、MIME、大小、文本可提取性 | 扫描件、图片、压缩包 |
| 文档解析 | 提取标题层级、段落、表格、页码/位置及原文 | 复杂版式还原、批注修订解析 |
| 要求提取 | 输出资格条件、废标条款、评分标准、时间节点、材料要求 | 法律意见、行业知识库 |
| 逐项匹配 | 对每条要求给出满足、部分满足、不满足、未找到或不确定 | 自动替用户修改投标文件 |
| 一致性检查 | 检查金额、日期、项目名称、工期候选值是否冲突 | 任意事实核验、互联网检索 |
| 结构化结论 | 风险等级、问题说明、证据、建议、置信度 | 无证据的自由发挥 |
| 人工复核 | 确认、忽略或修改结论；记录时间和修改内容 | 多人会签、权限流 |
| 历史与报告 | 浏览历史审查，导出 DOCX 与 JSON 报告 | 在线分享、电子签章 |
| 评测 | 固定 JSONL 样本集；记录模型、提示词版本和指标 | 自动调参平台、在线排行榜 |

### 1.4 结构化结果定义

结果分为三层，避免把“已满足项”和“风险问题”混在一起：

1. `Requirement`：从招标文件提取的原子要求。
2. `RequirementCheck`：每条要求与投标文件的匹配结果，包括已满足项。
3. `Finding`：仅保存需要人工关注的问题，包括未满足要求和一致性冲突。

`RequirementCheck` 至少包含：

- `requirement_id`
- `match_status`：`satisfied`、`partial`、`not_satisfied`、`not_found`、`uncertain`
- `tender_evidence[]`：招标侧块 ID、页码和原文摘录
- `bid_evidence[]`：投标侧块 ID、页码和原文摘录
- `searched_block_ids[]`：本次匹配实际检查过的投标块；`not_found` 必须保留检索范围
- `reason`
- `confidence`：0 到 1，仅表示 AI 对匹配判断的把握

每条 `Finding` 至少包含：

- `type`：`requirement_risk` 或 `consistency`
- `category`：资格条件、废标条款、评分标准、时间节点、材料要求、金额、日期、项目名称、工期
- `risk_level`：`high`、`medium`、`low`
- `title`、`description`、`suggestion`
- `requirement_check_id`：一致性问题可为空
- `evidence[]`：文档 ID、页码、块 ID、原文摘录
- `confidence`：0 到 1，界面显示为“AI 置信度”，不作为风险等级计算依据
- `review_status`：`pending`、`confirmed`、`ignored`、`modified`
- 修改后的标题、说明、等级和建议（仅人工修改时保存）

只有 `partial`、`not_satisfied`、`not_found`、`uncertain` 或一致性冲突生成 `Finding`；`satisfied` 保留在逐项匹配清单中，不要求人工逐条确认。

### 1.5 风险等级规则

- 高：废标条款或强制资格条件未满足/未找到；关键金额、项目名称或工期冲突。
- 中：强制要求部分满足/不确定；评分项缺失；可能影响履约或合规的日期冲突。
- 低：非强制材料、表达不清、格式或轻微一致性问题。

默认等级完全由“要求类别 + 是否强制 + 匹配状态 + 一致性字段类型”的确定性矩阵生成，LLM 不直接决定风险等级；人工可修改最终等级。

### 1.6 质量与安全要求

- 所有 API 请求和模型结果均做 Pydantic 校验。
- 上传文件使用生成的 UUID 文件名；拒绝路径穿越和超限文件。
- 原文证据必须能定位到已保存的解析块，报告不得引用不存在的证据。
- 日志不记录 API Key、完整文档正文或模型请求全文。
- 上传文档一律视为不可信数据；模型不得遵循文档中的指令，LLM 节点不授予文件写入、命令执行或网络访问工具。
- 文件上传、DOCX 解压、LibreOffice 转换、PDF 解析和模型调用均设置大小、页数、文本长度与执行超时上限。
- 样本仅允许虚构或脱敏内容，并在 README 和样本目录中声明。
- 产品输出仅供辅助审阅，不构成法律、招标或投标专业意见。

### 1.7 MVP 量化质量目标

固定评测集首版建议包含 6 至 10 组虚构文档对，覆盖五类招标要求和四类一致性字段。发布 MVP 前达到：

| 指标 | 目标 |
|---|---:|
| Pydantic 结构化输出成功率 | 100% |
| 引用块存在率 | 100% |
| 招标要求提取召回率 | ≥ 85% |
| 匹配状态 Macro-F1 | ≥ 75% |
| 一致性问题精确率 | ≥ 90% |
| 一致性问题召回率 | ≥ 80% |
| 证据页码准确率 | ≥ 90% |

严重问题漏检必须单独列出，不允许被平均分掩盖。首版基线若未达标，可以如实发布实际结果和限制，但不得省略失败案例。

### 1.8 DOCX 页码定位规则

LibreOffice 转 PDF 只负责得到分页结果，结构块到页码还需显式对齐：

1. 使用 `python-docx` 按原顺序提取标题、段落和表格。
2. 对 DOCX 块文本与转换后 PDF 文本做空白、换行和标点标准化。
3. 使用连续文本片段匹配页码；跨页块记录起始页。
4. 重复文本结合前后相邻块和文档顺序消歧。
5. 保存 `location_confidence`；无法可靠定位时页码为空并产生解析警告。
6. 任何进入最终结论的证据必须具有页码；低置信度页码在界面和报告中标记。

### 1.9 模型 API 可替换设计与公开仓库要求

业务工作流只调用一个最小 `ModelGateway`，不直接引用任何供应商名称。网关只提供项目当前需要的“结构化文本生成”能力；OpenAI Compatible API 和 Ollama 共用相同的输入输出模型，并在网关内部处理差异。

配置全部来自后端 `.env`：

```dotenv
MODEL_PROVIDER=openai_compatible
MODEL_BASE_URL=https://example.com/v1
MODEL_API_KEY=replace_me
MODEL_NAME=replace_me
MODEL_TEMPERATURE=0
MODEL_TIMEOUT_SECONDS=60
MODEL_MAX_RETRIES=2
MODEL_MAX_CONCURRENCY=1
```

切换到付费接口时，通常只修改 `MODEL_BASE_URL`、`MODEL_API_KEY` 和 `MODEL_NAME`。若供应商提供标准 OpenAI Compatible 接口，不新增适配器；只有真实请求/响应格式不兼容时，才增加最小供应商适配代码。

为兼容免费接口常见的限流和能力差异：

- LLM 调用默认串行，最大并发可配置。
- 对超时、HTTP 429 和可恢复的 5xx 最多重试两次并短暂退避。
- 不依赖某一家供应商专有的 structured output 功能；使用通用 JSON 提示加本地 Pydantic 校验。
- 启动时进行一次轻量模型连通性检查；失败只返回脱敏错误，不回显密钥。
- 模型能力不足或不支持预期上下文长度时明确失败，不静默截断关键证据。

公开 GitHub 仓库必须包含 `.env.example`、`.gitignore`、MIT License 和安全说明；不得提交 `.env`、API Key、SQLite 数据、上传文件、转换产物、完整模型请求日志、真实公司文件或含密钥截图。提交前运行密钥模式扫描和仓库内容检查。

---

## 2. MVP 用户流程

1. 用户进入“新建审查”，分别选择招标文件和投标文件。
2. 前端显示格式、大小与角色；后端校验并解析文件。
3. 用户查看解析摘要：文件名、页数、标题/段落/表格数量及解析警告。
4. 若使用远程 OpenAI Compatible API，页面明确提示文档候选片段会发送到外部服务；用户确认后点击“开始审查”。后端创建审查任务并返回审查 ID。
5. 固定 LangGraph 工作流依次建立候选检索、提取要求、逐项检索投标响应、运行一致性规则、合并并校验结论。
6. 前端轮询审查状态，展示进度和失败原因。
7. 审查进入“待人工复核”，用户可查看完整逐项匹配清单，并按风险等级和类别处理需要关注的结论及双侧原文证据。
8. 用户逐条确认、忽略或修改结论；未处理项保持待确认。
9. 用户完成复核后生成 DOCX/JSON 报告。
10. 审查及报告保留在历史记录中，可再次查看和下载。

异常流程：

- 扫描 PDF或无可提取文本：拒绝并提示 MVP 不支持 OCR。
- DOCX 无法转换页码：拒绝并提示安装/配置 LibreOffice。
- 模型配置不可用：任务标记失败，保留解析结果并允许重试。
- LLM 输出校验失败：节点最多重试一次；仍失败则任务失败并记录简短错误。
- 服务意外退出：启动时将遗留的 `running` 任务标记为可重试失败，用户从最近安全检查点重试。

---

## 3. 页面清单

| 页面 | 路由 | 核心内容 |
|---|---|---|
| 审查历史 | `/` | 审查名称、文件名、状态、风险统计、创建时间；进入详情或新建审查 |
| 新建审查 | `/reviews/new` | 双文件上传、类型/大小校验、解析摘要、解析警告、开始审查 |
| 审查工作台 | `/reviews/:id` | 进度；要求清单；风险筛选；证据对照；确认、忽略、修改；完成复核 |
| 报告预览 | `/reviews/:id/report` | 审查摘要、问题清单、人工状态、免责声明；下载 DOCX/JSON |
| 评测记录 | `/evals` | 运行评测、查看模型/提示词版本、整体指标和失败案例 |

全局只保留顶部导航、模型连接状态和错误提示。MVP 不单独建设设置页，模型配置由 `.env` 管控。

---

## 4. 后端 API 清单

统一前缀：`/api`。错误响应统一为 `{ "detail": "...", "code": "..." }`。

### 4.1 系统

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 服务、数据库、LibreOffice 与模型配置状态（不请求模型、不返回密钥） |
| POST | `/model/check` | 使用当前后端配置执行轻量连通性检查，返回供应商类型、模型名和脱敏错误 |

### 4.2 文档

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/documents` | `multipart/form-data` 上传单个文件；完成校验和解析。文档角色由创建审查时的字段决定 |
| GET | `/documents/{document_id}` | 获取元数据、解析统计和警告，不返回全文 |
| GET | `/documents/{document_id}/blocks` | 分页获取标题、段落、表格块及页码，供证据查看 |

### 4.3 审查与人工复核

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/reviews` | 传入两份文档 ID 和可选审查名称，创建并启动后台审查；返回 `202` |
| GET | `/reviews` | 分页查询历史，可按状态筛选 |
| GET | `/reviews/{review_id}` | 获取状态、阶段、进度、统计和错误摘要 |
| POST | `/reviews/{review_id}/retry` | 对失败任务从安全检查点重试 |
| GET | `/reviews/{review_id}/requirements` | 获取招标要求清单 |
| GET | `/reviews/{review_id}/requirement-checks` | 获取完整逐项匹配结果，可按匹配状态筛选 |
| GET | `/reviews/{review_id}/findings` | 获取需要关注的问题，按风险、类别、人工状态筛选 |
| PATCH | `/findings/{finding_id}` | 仅在 `awaiting_review` 状态确认、忽略或修改结论 |
| POST | `/reviews/{review_id}/finalize` | 校验所有风险发现已处理，通过 LangGraph resume 冻结审查 |
| GET | `/reviews/{review_id}/report?format=docx|json` | 按当前人工复核结果生成并下载报告 |

### 4.4 评测

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/eval-runs` | 使用仓库内固定评测集启动一次评测，返回 `202` |
| GET | `/eval-runs` | 获取历史评测运行 |
| GET | `/eval-runs/{run_id}` | 获取配置、指标和逐案例结果 |

MVP 不提供删除接口，避免误删审查证据；需要清理时停止服务后删除本地 `data/`。已完成审查禁止继续修改，多次下载报告必须基于同一冻结结果生成一致内容。

---

## 5. 数据库表设计

SQLite 开启外键。主键使用 UUID 文本，时间统一存 UTC ISO 8601。结构化数组/对象使用 JSON 文本，仅保存当前 MVP 会整体读写的字段。

### `documents`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 文档 ID |
| original_name | TEXT | 原始文件名 |
| stored_path | TEXT | 本地相对路径 |
| sha256 | TEXT | 文件指纹 |
| file_type | TEXT | `docx` / `pdf` |
| page_count | INTEGER | 页数 |
| text_char_count | INTEGER | 可提取文本字符数 |
| parse_status | TEXT | `processing` / `ready` / `failed` |
| parse_warning | TEXT NULL | 非致命警告 |
| created_at | TEXT | 创建时间 |

### `document_blocks`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 块 ID |
| document_id | TEXT FK | 所属文档，级联删除 |
| block_index | INTEGER | 文档内顺序 |
| block_type | TEXT | `heading` / `paragraph` / `table` |
| heading_level | INTEGER NULL | 标题层级 |
| page_number | INTEGER NULL | 1 起始页码；无法可靠定位时为空 |
| location_confidence | REAL | 页码定位置信度，0..1 |
| section_path | TEXT NULL | 所属标题路径，例如“第三章/资格审查” |
| content | TEXT | 段落文本或表格 JSON |
| search_text | TEXT | 用于全文检索的纯文本 |

约束：`UNIQUE(document_id, block_index)`。

使用 SQLite FTS5 为 `search_text` 建立派生全文索引；该索引可重建，不作为业务事实表。证据使用的块必须具有页码，低置信度定位在界面和报告中明确标记。

### `reviews`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 审查 ID |
| name | TEXT | 审查名称 |
| tender_document_id | TEXT FK | 招标文件 |
| bid_document_id | TEXT FK | 投标文件 |
| status | TEXT | `queued` / `running` / `awaiting_review` / `completed` / `failed` |
| current_stage | TEXT | 当前工作流节点 |
| workflow_thread_id | TEXT | LangGraph thread ID，MVP 与审查 ID 相同 |
| run_attempt | INTEGER | 当前执行次数，用于幂等重试 |
| model_provider | TEXT | `openai_compatible` / `ollama` |
| model_base_url | TEXT | 模型端点快照，不含查询密钥 |
| model_name | TEXT | 模型名快照 |
| prompt_version | TEXT | 提示词版本快照 |
| prompt_hash | TEXT | 实际提示词内容哈希 |
| model_parameters | TEXT | JSON，temperature 等参数，不含密钥 |
| error_message | TEXT NULL | 脱敏错误摘要 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### `requirements`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 要求 ID |
| review_id | TEXT FK | 所属审查，级联删除 |
| category | TEXT | 五类招标要求之一 |
| title | TEXT | 简短标题 |
| description | TEXT | 标准化要求 |
| sort_index | INTEGER | 在招标文件中的顺序 |
| mandatory | INTEGER | 0/1 |
| source_block_ids | TEXT | JSON 数组，招标原文块 ID |
| source_excerpt | TEXT | 招标原文摘录 |
| confidence | REAL | 0..1 |

### `requirement_checks`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 匹配检查 ID |
| review_id | TEXT FK | 所属审查，级联删除 |
| requirement_id | TEXT FK | 对应要求，级联删除 |
| match_status | TEXT | `satisfied` / `partial` / `not_satisfied` / `not_found` / `uncertain` |
| reason | TEXT | 匹配判断说明 |
| tender_evidence | TEXT | JSON 招标侧证据数组 |
| bid_evidence | TEXT | JSON 投标侧证据数组 |
| searched_block_ids | TEXT | JSON 投标候选块 ID 数组 |
| confidence | REAL | AI 匹配置信度，0..1 |

约束：`UNIQUE(review_id, requirement_id)`。`satisfied` 必须有投标证据；`not_found` 必须记录非空检索范围。

### `findings`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 发现 ID |
| review_id | TEXT FK | 所属审查，级联删除 |
| requirement_check_id | TEXT FK NULL | 对应匹配检查；一致性问题为空 |
| type | TEXT | `requirement_risk` / `consistency` |
| category | TEXT | 业务类别 |
| risk_level | TEXT | `high` / `medium` / `low` |
| title | TEXT | 问题标题 |
| description | TEXT | 问题说明 |
| suggestion | TEXT | 整改建议 |
| evidence | TEXT | JSON 证据数组，引用块 ID 和摘录 |
| confidence | REAL | 0..1 |
| review_status | TEXT | `pending` / `confirmed` / `ignored` / `modified` |
| reviewer_note | TEXT NULL | 人工备注 |
| override | TEXT NULL | JSON，仅保存人工覆盖字段 |
| reviewed_at | TEXT NULL | 复核时间 |

### `eval_runs`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 评测运行 ID |
| dataset_version | TEXT | 固定 JSONL 数据集版本 |
| model_provider | TEXT | 提供方快照 |
| model_base_url | TEXT | 模型端点快照，不含查询密钥 |
| model_name | TEXT | 模型快照 |
| prompt_version | TEXT | 提示词版本 |
| prompt_hash | TEXT | 实际提示词内容哈希 |
| model_parameters | TEXT | JSON，temperature 等可复现参数，不含密钥 |
| git_commit_sha | TEXT | 执行评测时的代码版本 |
| status | TEXT | `queued` / `running` / `completed` / `failed` |
| metrics | TEXT NULL | JSON 汇总指标 |
| duration_ms | INTEGER NULL | 总耗时 |
| input_tokens | INTEGER NULL | 输入 token |
| output_tokens | INTEGER NULL | 输出 token |
| estimated_cost | REAL NULL | 远程 API 估算成本；Ollama 可为空 |
| created_at | TEXT | 创建时间 |
| completed_at | TEXT NULL | 完成时间 |

### `eval_results`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT PK | 结果 ID |
| eval_run_id | TEXT FK | 所属运行，级联删除 |
| case_id | TEXT | 对应 `evals/cases.jsonl` 中的稳定 ID |
| passed | INTEGER | 0/1 |
| scores | TEXT | JSON 指标 |
| error_summary | TEXT NULL | 失败说明 |

不增加用户表、报告表和操作流水表：单用户无需用户表；完成审查后冻结结论，报告按冻结数据确定性生成；人工修改前值仍保留在 `findings` 原始字段，修改值放在 `override`。

所有枚举、布尔值、置信度范围和外键在 SQLite 层增加 `CHECK`/`FOREIGN KEY` 约束，并为常用外键与状态筛选字段建立索引。

---

## 6. LangGraph 状态和节点设计

### 6.1 状态

状态只传递 ID、阶段产物和控制信息，不塞入完整文件二进制。

```text
ReviewState
├─ review_id: str
├─ tender_document_id: str
├─ bid_document_id: str
├─ requirement_ids: list[str]
├─ requirement_check_ids: list[str]
├─ finding_ids: list[str]
├─ current_stage: str
├─ warnings: list[str]
├─ error: str | null
├─ failed_node: str | null
├─ run_attempt: int
└─ retry_count: int
```

模型配置、提示词版本和状态持久化在 `reviews`，文档正文通过块 ID 按需读取。LangGraph 使用 SQLite checkpoint；业务表仍由应用仓储函数写入，checkpoint 不作为业务查询接口。

### 6.2 固定工作流

```text
START
  │
  ▼
load_and_validate_documents            确定性
  │
  ▼
build_search_index                     确定性 / SQLite FTS5
  │
  ▼
extract_requirements_in_batches        LLM + Pydantic
  │
  ▼
normalize_and_validate_requirements    确定性
  │
  ▼
retrieve_bid_candidates                确定性 / 每条要求
  │
  ▼
match_bid_responses                    LLM + Pydantic
  │
  ├─────────────────────────┐
  ▼                         ▼
build_requirement_findings   run_consistency_rules
确定性风险矩阵               确定性规则；LLM 仅解歧义
  └───────────────┬─────────┘
                  ▼
merge_and_deduplicate_findings         确定性
                  │
                  ▼
evidence_and_schema_gate               确定性
                  │
          ┌───────┴────────┐
          │通过             │失败且未重试
          ▼                 ▼
persist_for_human_review    retry_failed_llm_node（最多一次）
          │
          ▼
AWAITING_HUMAN_REVIEW                  人工复核边界
          │ POST /finalize → resume
          ▼
finalize_and_freeze_review             确定性
          │
          ▼
END
```

### 6.3 节点职责

| 节点 | 类型 | 输入/输出与约束 |
|---|---|---|
| `load_and_validate_documents` | 确定性 | 校验两个文档角色、解析状态及块可用性 |
| `build_search_index` | 确定性 | 建立/校验 SQLite FTS5 索引与标题路径 |
| `extract_requirements_in_batches` | LLM | 按章节分批从招标块输出五类原子要求；每项必须引用块 ID |
| `normalize_and_validate_requirements` | 确定性 | 去空、枚举归一、置信度范围和证据存在性校验 |
| `retrieve_bid_candidates` | 确定性 | 按标题、关键词、FTS5 和相邻块窗口为每条要求选取投标候选块 |
| `match_bid_responses` | LLM | 仅基于要求与候选块生成 `RequirementCheck`；保留双方证据和检索范围 |
| `build_requirement_findings` | 确定性 | 使用风险矩阵将非满足匹配转换为可人工复核的问题 |
| `run_consistency_rules` | 确定性为主 | 正则/标准化提取金额、日期、项目名称、工期并查找冲突；仅对规则无法判定的候选调用 LLM 解歧义 |
| `merge_and_deduplicate_findings` | 确定性 | 按类别、要求、证据块合并重复发现 |
| `evidence_and_schema_gate` | 确定性 | Pydantic、双侧证据、实际引用文本、检索范围、必填字段和风险映射校验 |
| `persist_for_human_review` | 确定性 | 原子写入要求、匹配和发现，状态改为 `awaiting_review` |
| `finalize_and_freeze_review` | 人工触发后的确定性节点 | 确认无待处理风险发现，冻结结论并将状态改为 `completed` |

人工复核不包装成“审核智能体”。图在持久化后停止，由 REST 接口接收人工决定，再触发最终节点。

### 6.4 运行、恢复与幂等规则

- 一个 `review_id` 对应一个 LangGraph `thread_id`，同一审查同一时刻只允许一个运行实例。
- 每次启动或重试递增 `run_attempt`；节点按 `(review_id, run_attempt, stage)` 覆盖本阶段产物，避免重复插入。
- LLM 结构校验失败只在原节点重试一次，不从头重复解析文件。
- 服务启动时将遗留的 `running` 审查标记为 `failed` 且可重试。
- `PATCH /findings/{id}` 只允许在 `awaiting_review` 状态执行。
- `/finalize` 检查所有风险发现已处理后，通过对应 thread 恢复图并冻结结果。
- `completed` 审查不可修改；需要更换模型或重新审查时创建新的审查记录。

---

## 7. GitHub Issues 任务拆分

标签建议：`phase:1` 至 `phase:4`、`frontend`、`backend`、`workflow`、`eval`、`docs`、`bug`。每个 Issue 都写清范围、验收条件和明确不做项。

### Milestone 0：方案确认

1. `docs: 确认 MVP PRD 与非目标`
2. `docs: 确认数据模型、API 与 LangGraph 边界`

### Milestone 1：项目骨架与文档解析闭环

3. `chore: 初始化 Vue 3 + TypeScript + Vite 前端`
4. `chore: 初始化 FastAPI + SQLite 后端和环境配置`
5. `feat: 实现 DOCX 与文本 PDF 上传校验`
6. `feat: 解析标题、段落、表格和 DOCX/PDF 页码定位`
7. `feat: 建立标题路径和 SQLite FTS5 文档索引`
8. `feat: 实现新建审查页与解析摘要`
9. `docs: 建立 README 骨架、架构图、模型配置、远程数据提示与免责声明`
10. `chore: 添加 .env.example、.gitignore、MIT License 和公开仓库检查`
11. `chore: 添加虚构样本和解析冒烟脚本`

### Milestone 2：受控审查工作流

12. `feat: 实现可配置 ModelGateway 与模型连通性检查`
13. `feat: 接入 OpenAI Compatible 与 Ollama，处理限流、超时和重试`
14. `feat: 实现招标要求分批提取节点与结构校验`
15. `feat: 实现投标候选检索和逐项 RequirementCheck`
16. `feat: 实现确定性风险矩阵与风险 Finding 生成`
17. `feat: 实现金额、日期、项目名称和工期一致性规则`
18. `feat: 组装 LangGraph 固定工作流与 SQLite checkpoint`
19. `feat: 实现后台审查状态、幂等重试和启动恢复`

### Milestone 3：人工复核与报告

20. `feat: 实现审查历史、逐项匹配清单和工作台`
21. `feat: 实现发现筛选、证据对照与人工处置`
22. `feat: 冻结审查并生成一致的 DOCX 与 JSON 报告`
23. `docs: 完善启动说明、截图和免责声明`

### Milestone 4：固定评测集与发布准备

24. `eval: 建立带要求、匹配、证据和一致性标注的固定评测集`
25. `eval: 实现质量、耗时、token、成本和版本指标记录`
26. `eval: 展示严重漏检与逐案例失败原因`
27. `docs: 补充评测结果、限制与复现步骤`
28. `chore: 完成接口冒烟、密钥扫描和 GitHub 发布检查`

建议提交信息示例：

- `chore: initialize frontend and backend`
- `feat(parser): parse docx headings tables and pages`
- `feat(review): add controlled langgraph workflow`
- `fix(parser): reject image-only pdf files`
- `eval: add requirement matching baseline`
- `docs: add architecture and local setup`

一个 Issue 可包含前后端最小闭环，不为“每层一个文件”制造额外 Issue；提交应小而可运行。

---

## 8. 第一阶段验收标准

第一阶段定义为“项目骨架与文档解析闭环”，只证明前后端、本地存储和解析链路可靠，不提前接入 LLM。

### 功能验收

- 可按 README 在 Windows 本地分别启动前端和后端。
- `.env.example` 包含全部配置名但没有真实密钥；`.env`、`data/` 和上传文件不会进入 Git。
- 仓库包含 MIT License；README 说明免费接口不保证长期额度，切换供应商只需修改 `.env`。
- 用户可上传一份虚构招标 DOCX 和一份虚构投标文本 PDF。
- 后端拒绝不支持类型、超限文件、扫描/无文本 PDF 和角色错误，并返回可理解错误。
- DOCX 能提取标题、段落、表格；通过 LibreOffice 转换获得页码。
- PDF 能按页提取文本，并尽可能识别表格；无法可靠识别的内容仍作为段落保留并给出警告。
- DOCX 块与转换后 PDF 的页码对齐覆盖率在固定样本上达到 90% 以上；无法可靠定位的块不得伪造页码。
- 标题路径和 SQLite FTS5 索引可按关键词返回对应块及前后相邻块。
- 页面展示两份文档的文件名、页数、标题数、段落数、表格数和警告。
- 数据库保存文档元数据和解析块，重启服务后仍可读取。

### 工程验收

- 后端暴露 `/api/health`、文档上传、文档详情和文档块查询接口，OpenAPI 可访问。
- 使用 Pydantic 校验请求、响应和解析结构。
- 所有源文件使用 UTF-8；不生成独立单元测试文件。
- 提供一个可重复运行的接口冒烟脚本：健康检查 → 上传两份样本 → 查询解析结果与 FTS 命中；退出码明确表示成功或失败。
- 对虚构样本人工抽查：标题、段落、表格顺序正确，页码引用可回到转换后 PDF 对应页。
- README 已包含功能范围、当前架构、工作流占位图、启动步骤、样本声明和免责声明；截图与评测结果标记为后续里程碑补充，不伪造内容。
- `git status` 中无密钥、数据库、上传件、转换中间件或真实业务文件。
- 公开仓库检查能够扫描常见 API Key 模式，并确认 `.env`、日志和样本中无凭据。
- 第一阶段相关 Conventional Commits 清晰，所有 Phase 1 Issues 验收后再开始模型工作流。

### 第一阶段明确不做

不接入 LLM、不实现要求提取/匹配、不做一致性规则、不做人工复核、不生成最终报告、不做评测执行器。这些功能分别进入后续里程碑。

---

## 待确认的默认方案

若无调整，后续初始化将采用：前后端单仓库；前端 Element Plus；后端 FastAPI；SQLite + FTS5；`python-docx` 解析 DOCX 结构；LibreOffice headless 转换并对齐页码；PyMuPDF 解析文本 PDF；通过 `.env` 可替换的最小 ModelGateway，开发阶段优先免费 OpenAI Compatible API 或 Ollama；Requirement、RequirementCheck、Finding 三层结果；确定性风险矩阵；报告导出 DOCX/JSON；固定 JSONL 评测集；不引入供应商专有业务代码、额外仓储抽象、任务队列、向量库或多智能体框架。
