# LLM Knowledge Base Design — 基于 Karpathy 方法的改进方案

> 讨论日期：2026-04-09
> 参考：Karpathy 的个人 LLM 知识库方法论

## Karpathy 方法六大支柱

| 支柱 | 核心思想 |
|------|---------|
| **Data Ingest** | raw/ 目录存原始文档 → LLM 逐步"编译"成互相链接的 wiki |
| **IDE** | Obsidian 作前端，LLM 写入和维护所有数据，人很少手动编辑 |
| **Q&A** | wiki 足够大后（~100篇/40万词），LLM agent 直接在 wiki 上回答复杂问题 |
| **Output** | 渲染成 md/slides/图表 → 查看 → 归档回 wiki（复合循环） |
| **Lint** | LLM 健康检查：一致性、缺失、新连接、下一步建议 |
| **Extra Tools** | 小型搜索引擎、CLI 工具供 LLM 调用 |

## 我们现有系统 vs Karpathy 方法

### 已有的

| 能力 | 现状 | 对应 Karpathy |
|------|------|---------------|
| 论文分析页生成 | `wiki_compiler.compile_paper_page()` — 全文抓取 + Claude 分析 | Data Ingest (部分) |
| 概念页生成/更新 | `wiki_compiler.create/update_concept_page()` | Data Ingest (部分) |
| Obsidian vault | `wiki/.obsidian/` 配置已有 | IDE (基础) |
| 基础 lint | `wiki_compiler.lint_wiki()` — 孤立论文、空概念页、重复检测 | Lint (初级) |
| 自动触发 | daily pipeline 对 High 论文自动编译 | 自动化 |

### 缺失的（Gap Analysis）

| Gap | 描述 | 优先级 |
|-----|------|--------|
| **raw/ 目录** | 没有原始文档存储层，论文全文只在编译时临时抓取，不持久化 | 高 |
| **索引系统** | 没有全局索引文件（papers index, concept index, topic map），LLM 无法高效导航 | 高 |
| **Q&A 能力** | 无法对 wiki 提问，没有 agent 能读 wiki 回答问题 | 高 |
| **复合循环** | Q&A 输出不会归档回 wiki，知识不会累积 | 高 |
| **可视化输出** | 没有 Marp slides / matplotlib 图表生成 | 中 |
| **深度 Lint** | 现有 lint 只检查结构，不检查内容一致性、不补全缺失信息 | 中 |
| **手动摄入** | 没有 Web Clipper 或手动添加论文/文章到 raw/ 的工作流 | 中 |
| **搜索引擎** | 没有 wiki 搜索工具供 LLM 或人使用 | 低→中 |
| **图片支持** | wiki 页面没有图片引用 | 低 |

## 讨论记录

### Round 1: 差距分析与优先级

**现状总结**：
- wiki 规模很小：2 papers, 4 concepts, ~700 行, 112KB
- Karpathy 的参考规模：~100 篇文章, ~40 万词
- 我们的 wiki 目前是"只写不读"——pipeline 生成内容后没有消费者
- 最大的结构性缺失：没有 raw/ 层、没有索引、没有 Q&A 闭环

**核心问题**：我们的 wiki 现在是一个单向管道的末端产物。Karpathy 方法的精髓在于 wiki 是一个**活的知识实体**——它既被读取（Q&A）又被写入（ingest + Q&A 归档），形成正反馈循环。

待讨论：
1. raw/ 层应该存什么？怎么摄入？
2. 索引系统怎么设计才能让 LLM agent 高效导航？
3. Q&A 的交互模式是什么？怎么让输出归档回 wiki？

### Round 2: Raw 层设计 + 关联索引 + 摄入工作流

#### Q1: 论文有 repo 怎么索引？论文间关联怎么索引？

**结论：per-paper 目录结构，repo 作为附属资产**

```
wiki/raw/papers/2604.07331/
├── meta.yaml          ← 元数据
├── paper.pdf          ← PDF 原件
├── fulltext.md        ← 抽取的全文
├── repo-readme.md     ← repo README（如有）
└── figures/           ← 关键图（可选）
```

- 论文的 repo README 存在 raw 目录里，LLM 编译时同时读取论文 + repo 内容
- 独立框架/工具（Isaac Gym、MuJoCo）需要单独的 wiki 页面
- 普通论文的 repo 不需要单独页面，融入论文分析页即可

**论文间关联：通过概念页作为中间节点自然形成**

```
Paper A ──[[Diffusion Policy]]──┐
                                ├── 概念页（hub node）
Paper B ──[[Diffusion Policy]]──┘
```

- Obsidian Graph View 自动可视化这些链接
- 推荐使用 typed links：在文中用自然语言描述关系类型（延伸、对比、使用）
- 不需要手动维护关联图——LLM 在编译时通过 `[[]]` 链接自然创建

#### Q2: 电脑上浏览时怎么快速摄入？

**两条路径：**

1. **Zotero → Obsidian 同步链**（适合系统性收集）
   - 浏览器 Zotero Connector → Zotero 存 PDF → Obsidian Zotero Integration 插件同步 → LLM 检测新 raw → 编译

2. **直接给 Claude URL**（快速通道）
   - 给 arXiv URL → 自动：抓元数据 + 下载 PDF + 全文抽取 + 存 raw/ + 编译 wiki

**相关 Obsidian 插件：**
- Obsidian Web Clipper（官方）—— 博客/网页
- Paper Clipper —— DOI 导入论文
- Zotero Integration —— Zotero 文献同步
- ReadItLater —— Ctrl+Shift+K 快速收集

#### Q3: 先讨论清楚再冷启动 ✓

冷启动前还需要敲定：
- [ ] raw/ 目录结构和 meta.yaml schema
- [ ] 索引系统设计（INDEX.md, TOPIC-MAP.md）
- [x] 编译 prompt 改进 → Round 4 详细设计
- [ ] 冷启动策略（510 篇全量 vs 渐进式）

### Round 4: 编译流程重新设计（First Principles）

#### 核心认知

编译 = 把原始信息转化为结构化的、互相连接的知识。

现有问题：4 个 prompt 是实现 wiki_compiler.py 时快速写的，没有经过迭代。
Wiki 只编译了 2 篇论文 4 个概念，prompt 质量未经验证。
不应该在旧 prompt 上打补丁，而是从第一性原理重新设计。

#### 两步编译模型

```
Step 1: 理解 + 分析 + 分类
        人类类比：读一篇新论文，理解它在已有知识中的位置
        输入: raw item 全部内容 + wiki 上下文（概念索引 + 主题地图）
        输出: 论文分析页（frontmatter 承载结构化信息，正文承载深度分析）

Step 2: 知识整合
        人类类比：读完后更新你脑子里的知识结构
        输入: Step 1 输出 + 需要更新的概念页
        输出: 更新后的概念页（批量，含新建和更新）
```

#### Step 1 Prompt 设计

**完整输入模板：**

```
你是一个研究知识库的编译器。你的任务是分析一篇新论文，将它编译成知识库的一个页面。

## 原始数据

{meta.yaml 内容}

{fulltext.md 或 abstract}

{repo-readme.md（如有）}

## 知识库当前状态

### 概念索引
{concepts/INDEX.md 内容}

### 主题地图
{TOPIC-MAP.md 内容}

## 输出要求

输出一个完整的 Markdown 文件，包含两部分：

### Part A: YAML Frontmatter

必须包含以下字段：
- title, arxiv_id, date, venue, authors, url
- repo_url（如有）
- raw: "raw/papers/{id}" （指向原始数据路径）
- compiled: 今天日期
- summary: 一句话摘要（中文，<100字，供索引使用）
- concepts: 数组，每个元素包含：
  - name: 概念名（英文，使用知识库中已有名称优先）
  - relation: extends | compares | uses | introduces
  - detail: 一句话说明关系（中文）
- new_concepts: 数组（只包含知识库中不存在的新概念），每个元素包含：
  - name: 概念名
  - suggested_topic: 在主题地图中的建议位置（格式："父主题 > 子主题"）
  - description: 一行描述（中文，供索引使用）

### Part B: 正文（深度分析）

写一篇深度分析文章（中文），让该领域的研究者读完后能理解：
- 这篇论文做了什么
- 为什么重要
- 和已有工作什么关系
- 有什么局限

要求：
1. 用 [[概念名]] 格式创建 Obsidian 反向链接
2. 关系要 typed：明确写"延伸了 [[X]]"、"对比 [[Y]]"、"使用了 [[Z]]"
3. 如果有 repo，分析实现细节和论文描述的异同
4. 不要使用固定模板——根据论文类型（方法/系统/综述）自行组织最合适的结构
5. 分析要深入具体，不要泛泛而谈
6. 直接输出 Markdown，不要输出解释、对话或元评论
```

**设计决策说明：**
- 不预设 section 模板（核心方法/关键创新/...），让 LLM 根据论文类型自行判断结构
- frontmatter 中 concepts 已经包含 relation type，合并了原来的"概念提取"步骤
- new_concepts 包含 suggested_topic，合并了原来需要单独做的"分类"步骤
- 一次调用完成：论文分析 + 概念提取 + 关系标注 + 主题归类

#### Step 2 Prompt 设计

**完整输入模板：**

```
你是一个研究知识库的编译器。一篇新论文刚刚被编译到知识库中。
你的任务是将新论文的知识整合到相关的概念页面中。

## 新编译的论文

### Frontmatter
{Step 1 输出的 frontmatter}

### 分析摘要
{Step 1 输出的正文前 3000 字}

## 需要更新的概念页

{对每个相关概念，列出当前内容}

### 概念: {concept_name_1}
```markdown
{现有概念页完整内容}
```

### 概念: {concept_name_2}
```markdown
{现有概念页完整内容}
```

## 需要新建的概念页

{列出 new_concepts}
- {name}: {description}（建议位置: {suggested_topic}）

## 输出要求

对每个概念输出更新/新建后的完整页面，用分隔符区分：

对于**已有概念**：
===CONCEPT: {概念名}===
（输出更新后的完整 Markdown，包含 frontmatter）

对于**新概念**：
===NEW_CONCEPT: {概念名}===
（输出新建的完整 Markdown，包含 frontmatter）

### 更新策略

已有概念页的更新必须是**有机整合**，不是追加：
- 新论文推进了该概念 → 融入"发展历程"
- 新论文应用该概念到新场景 → 扩展"应用"
- 新论文对比/改进了已有方法 → 更新对比分析
- 新论文解决了已提到的局限 → 更新局限性讨论

### 概念页 frontmatter 格式

```yaml
---
concept: "概念名"
created: "首次创建日期"
updated: "今天日期"
papers:
  - "arxiv_id_1"
  - "arxiv_id_2"
parent_topic: "主题地图中的父主题"
description: "一行描述（中文，供索引使用）"
---
```

### 概念页正文要求

1. 使用 [[论文标题]] 或 [[arxiv_id]] 创建反向链接
2. 全文中文
3. 不要简单追加段落——重新组织使内容连贯
4. 直接输出 Markdown，不要输出解释、对话或元评论
```

**设计决策说明：**
- 只传正文前 3000 字给 Step 2（Step 2 不需要论文全文，frontmatter + 摘要足够理解关系）
- 批量处理所有概念（新建 + 更新），一次调用
- 分隔符 `===CONCEPT:` 让程序可靠地拆分输出
- 如果某个概念页特别长导致 context 不够，可以降级为逐个更新

#### 编译后的程序化处理

Step 1 和 Step 2 完成后，程序（不是 LLM）执行：

```
1. 解析 Step 1 frontmatter → 提取 summary, concepts, new_concepts
2. 解析 Step 2 输出 → 按分隔符拆分，写入各概念页
3. 更新 papers/INDEX.md → 插入新论文行（程序从 frontmatter 读数据）
4. 更新 concepts/INDEX.md → 插入新概念行（如有）
5. 更新 INDEX.md → recent + stats
6. 标记 raw/meta.yaml compile_status.stale = false
```

TOPIC-MAP.md 不在每次编译后自动更新——在 lint 时由 LLM 统一审视和调整。

#### 与旧架构的对比

| | 旧 | 新 |
|--|---|---|
| LLM 调用次数/篇 | 3-7 次 | 2 次 |
| 预估耗时/篇 | 10-14 min | 4-6 min |
| 概念提取 | 独立步骤 | 合并到 Step 1 |
| 关系标注 | 无 | frontmatter 里结构化 |
| 索引更新 | 无 | 程序自动从 frontmatter 提取 |
| 正文结构 | 固定5个section | LLM 自行判断 |
| repo 分析 | 无 | Step 1 输入包含 repo README |

### Round 5: Q&A + 复合循环设计

#### 核心认知

Q&A 不只是"问问题得答案"——**Q&A 本身就是知识生产活动**。
每次提问都可能产生新洞见、新联系、新综合，这些应该成为 wiki 的一部分。

Karpathy: "我自己的探索和提问，都会不断沉淀进这个知识库里，形成累积效应。"

#### Q&A Agent = Claude Code

不需要额外造东西。Claude Code 已有 Read/Grep/Glob 工具，wiki 就是磁盘上的文件。
缺的不是能力，缺的是：
1. **导航协议** — Claude 怎么知道从 wiki/INDEX.md 开始
2. **归档机制** — 回答怎么变成 wiki 页面

#### 导航协议

写进 CLAUDE.md 或做成 skill：

```
当回答研究相关问题时：
1. 读 wiki/INDEX.md          → 全局地图
2. 根据问题类型选择入口：
   - 特定论文 → papers/INDEX.md → 具体页面
   - 概念/方法 → concepts/INDEX.md → 具体页面
   - 跨领域综合 → TOPIC-MAP.md → 相关概念群 → 多个页面
3. 跟 [[]] 链接继续深入
4. 如果 wiki 不覆盖 → 说明边界，建议补充
```

#### 归档机制

**什么值得归档：** 产生了新知识的 Q&A 才归档（综合分析、研究方向、文献综述、联系发现）。
简单事实查询（答案已在论文页里的）不归档。

**触发方式：** 用户主动说"存进 wiki"。低摩擦但有意识。

**目录结构：**

```
wiki/
├── insights/                     ← Q&A 归档：基于已有知识的综合分析（回顾性）
│   ├── INDEX.md
│   ├── compare-diffusion-vs-flow-matching.md
│   └── survey-sim-to-real-methods.md
├── ideas/                        ← 研究 idea：面向未来的方向提案（前瞻性）
│   ├── INDEX.md
│   └── reactive-loco-manipulation.md
```

**归档页格式：**

```yaml
---
type: insight              # insight | idea | survey | comparison
title: "Diffusion Policy vs Flow Matching：操作任务对比分析"
date: "2026-04-09"
trigger: "用户提问"
concepts:
  - "Diffusion Policy"
  - "Flow Matching Policy"
papers:
  - "2604.xxxxx"
  - "2501.xxxxx"
summary: "一行摘要"
---

（正文：结构化分析，带 [[]] 链接）
```

**归档不是原样复制对话——重新编译成 wiki 格式**（frontmatter + [[]] 链接 + 结构化）。

#### 复合循环

```
Q&A 归档 ──→ insights/INDEX.md 更新
         ──→ INDEX.md "Recent Insights" 更新
         ──→ 相关概念页获得 Obsidian backlinks（自动）
         ──→ 可能触发概念页更新（发现新联系时）
```

**累积效应示例：**

```
Day 1: 编译 10 篇 diffusion policy 论文
Day 2: 用户问 "diffusion policy 推理速度问题有哪些解法？"
       → Claude 综合 wiki 回答 → 归档为 insight
       → insight 链接到 [[Consistency Policy]] [[Flow Matching Policy]]
Day 3: 新论文编译时，Step 1 能看到这个 insight（通过 INDEX.md）
       → 论文分析自然引用之前的分析框架
Day 5: 用户再问推理加速方向现状
       → Claude 不仅读论文，还读到 Day 2 的 insight
       → 回答更完整（有之前的综合分析打底）
```

**wiki 的三种增长来源：**
1. 外部摄入（新论文/文章编译） → papers/, concepts/
2. Q&A 沉淀（综合分析归档） → insights/
3. 研究探索（idea 提案） → ideas/

三者互相增强：更多论文 → Q&A 更好 → 更多 insight → 编译更好 → ...

### Round 3: Raw 更新策略 + 索引系统详细设计

> 核心认知：raw 更新和 index 系统是**解耦的**。
> raw 更新是数据层的事，index 是导航层的事。
> 唯一交叉点：raw 更新 → wiki 重编译 → index 更新。

---

## 一、Raw 数据层设计

### 1.1 meta.yaml Schema

每个 raw item 都有一个 meta.yaml 作为结构化元数据：

```yaml
# wiki/raw/papers/2604.07331/meta.yaml
id: "2604.07331"
type: paper                    # paper | article | repo | dataset
title: "RoSHI: Robot-Human Simultaneous Interaction"
authors:
  - "Author A"
  - "Author B"
date: "2026.04"
venue: "arXiv"
url: "https://arxiv.org/abs/2604.07331"
pdf_url: "https://arxiv.org/pdf/2604.07331"

# 关联资产
repo_url: "https://github.com/xxx/roshi"   # 可选
project_url: "https://roshi-project.com"    # 可选
has_code: true

# 生命周期
fetched_at: "2026-04-09"         # 首次抓取时间
updated_at: "2026-04-09"         # 最近更新时间
version: 1                       # arXiv 版本号
venue_status: "preprint"         # preprint | accepted | published

# 资产清单（实际存在的文件）
assets:
  - paper.pdf
  - fulltext.md
  - repo-readme.md

# 编译状态（由编译器写入，不由人编辑）
compile_status:
  compiled_at: "2026-04-09"      # 最近编译时间
  wiki_page: "papers/2604.07331.md"
  stale: false                   # raw 更新后 wiki 未重编译 → true
```

### 1.2 Raw 更新场景和策略

| 场景 | 触发条件 | 更新动作 |
|------|---------|---------|
| arXiv 新版本 | v1 → v2 | 重新下载 PDF + fulltext，version++ |
| 论文被会议接收 | venue 变化 | 更新 venue/venue_status |
| repo 出现或更新 | 首次发现 / 重大更新 | 抓取 repo-readme.md |
| 项目页出现 | project_url 新增 | 更新 meta.yaml |
| 引用数变化 | 定期检查 | 更新 citation_count（可选） |

### 1.3 更新机制

**原则：raw/ 只由外部数据源驱动更新，LLM 编译器不修改 raw/**

```
外部源 (arXiv/GitHub/S2)
        │
        ▼
  raw_updater.py            ← 新脚本：检查并更新 raw 数据
        │
        ├── 对比 meta.yaml 与外部源
        ├── 有变化 → 更新文件 + updated_at + stale=true
        └── 无变化 → 跳过
        │
        ▼
  编译器检测 stale=true → 重编译 wiki 页面 → stale=false
```

**更新频率：**
- 论文 PDF/全文：不频繁，只在版本变化时
- repo README：可以在 daily pipeline 里顺带检查
- venue_status：可以在 lint 时检查（arXiv preprint 半年后看是否被接收）

**关键：更新是幂等的。** 重跑 raw_updater 对没变化的数据不产生副作用。

### 1.4 非论文类型的 raw 结构

```yaml
# wiki/raw/articles/scaling-robot-data/meta.yaml
id: "scaling-robot-data"
type: article
title: "Scaling Robot Data Collection"
authors: ["Blog Author"]
date: "2026.03"
url: "https://blog.example.com/scaling-robot-data"
fetched_at: "2026-04-09"
assets:
  - content.md              # Web Clipper 或 trafilatura 抽取的全文
  - images/figure1.png      # 文章中的关键图

# wiki/raw/repos/isaac-lab/meta.yaml
id: "isaac-lab"
type: repo
title: "Isaac Lab"
url: "https://github.com/isaac-sim/IsaacLab"
fetched_at: "2026-04-09"
assets:
  - readme.md
  - structure.md            # 仓库结构概要（LLM 或工具生成）
```

---

## 二、索引系统设计

### 2.1 架构总览

```
wiki/
├── INDEX.md              ← L0: 全局入口（~80行, ~2K tokens）
├── TOPIC-MAP.md          ← L1: 语义地图（~100行, ~3K tokens）
├── papers/
│   ├── INDEX.md          ← L1: 论文目录（~500行 @500篇, ~15K tokens）
│   └── *.md              ← L2: 论文分析页
├── concepts/
│   ├── INDEX.md          ← L1: 概念目录（~60行 @50概念, ~2K tokens）
│   └── *.md              ← L2: 概念页
└── raw/
    └── ...               ← 不需要索引（通过 meta.yaml 自描述）
```

LLM 导航路径：`INDEX.md → 判断去哪 → papers/INDEX.md 或 concepts/INDEX.md → 具体页面`

### 2.2 INDEX.md（全局入口）

**目的**：LLM 读一个文件就知道 wiki 全貌。
**维护方式**：程序自动生成（stats + recent）+ LLM 写摘要（topic overview）。
**更新频率**：每次编译后自动重建。

```markdown
# Robot Learning Research Wiki

> Last updated: 2026-04-09 | 513 papers · 47 concepts · 8 topics

## Navigation

| Resource | Description |
|----------|-------------|
| [Paper Index](papers/INDEX.md) | 所有论文一行摘要，按年份分组 |
| [Concept Index](concepts/INDEX.md) | 所有概念一行描述，按字母排序 |
| [Topic Map](TOPIC-MAP.md) | 研究方向层次树，概念间上下级关系 |

## Recent (last 7 days)

| Date | Paper | Relevance | Concepts |
|------|-------|-----------|----------|
| 2026-04-09 | [[2604.07331]] RoSHI | High | [[Teleoperation]], [[Whole-Body Control]] |

## Topic Overview

| Topic | Papers | Core Concepts |
|-------|--------|---------------|
| Loco-Manipulation | 174 | Whole-Body Control, MPC, RL Policy |
| Locomotion | 94 | Sim-to-Real, Terrain Adaptation, CPG |
| Manipulation | 57 | Diffusion Policy, Grasping, Dexterous |
| Hardware | 38 | Actuator Design, Sensor Integration |
| Teleoperation | 30 | Motion Capture, VR Interface |
| ... | | |

## Wiki Health

- Stale papers (raw updated, wiki not re-compiled): 0
- Orphan papers (no concepts linked): 0
- Concepts with < 2 papers: 3
```

### 2.3 papers/INDEX.md（论文目录）

**目的**：LLM 扫一遍就能找到相关论文，不用逐个打开。
**维护方式**：程序生成结构 + LLM 写每篇的一句话摘要。
**关键设计**：每行必须包含 concepts 标签，这样 LLM 可以用 grep 式思维快速定位。

```markdown
# Paper Index

> 513 papers, sorted by date descending

## 2026

| ID | Title | Date | Summary | Concepts |
|----|-------|------|---------|----------|
| [[2604.07331]] | RoSHI | 2026.04 | 人形全身遥操作，动捕数据驱动 | [[Teleoperation]], [[Whole-Body Control]] |

## 2025

| ID | Title | Date | Summary | Concepts |
|----|-------|------|---------|----------|
| [[2501.xxxxx]] | ... | 2025.01 | ... | [[...]] |

## 2024

...
```

**规模估算 @500 篇**：
- 每行 ~150 字符
- 500 行 + 表头 ≈ ~80K 字符 ≈ ~20K tokens
- 可接受。超过 1000 篇时拆成 papers/INDEX-2026.md, papers/INDEX-2025.md

### 2.4 concepts/INDEX.md（概念目录）

**目的**：概念全景，LLM 快速了解知识库覆盖了哪些概念。
**维护方式**：程序生成（计数）+ LLM 写描述。

```markdown
# Concept Index

> 47 concepts, sorted alphabetically

| Concept | Papers | Description |
|---------|--------|-------------|
| [[Action Chunking]] | 8 | 动作分块：一次生成多步动作序列保证时序一致性 |
| [[Behavior Cloning]] | 15 | 行为克隆：直接从专家示范学习策略映射 |
| [[Diffusion Policy]] | 12 | 扩散模型应用于机器人动作生成的策略框架 |
| [[Domain Randomization]] | 9 | 通过随机化仿真参数提高 sim-to-real 迁移鲁棒性 |
| [[Dexterous Manipulation]] | 7 | 灵巧手精细操作 |
| ... | | |
```

~50 概念 × ~100 字符/行 ≈ ~5K 字符，非常轻量。

### 2.5 TOPIC-MAP.md（语义地图）

**目的**：表达概念间的层次和语义关系，是知识库的"骨架"。
**维护方式**：LLM 维护（lint 时重新审视结构，建议拆分/合并）。
**这是唯一一个主要由 LLM 维护的索引文件。**

```markdown
# Topic Map

> 研究方向 → 子方向 → 核心概念的层次结构

## Locomotion & Loco-Manipulation
- [[Whole-Body Control]]
  - [[Model Predictive Control]]
  - [[Centroidal Dynamics]]
- [[Locomotion]]
  - [[Sim-to-Real Transfer]]
  - [[Terrain Adaptation]]
  - [[Central Pattern Generator]]
- [[Loco-Manipulation]]
  - [[Dual-Arm Mobile Manipulation]]

## Manipulation
- [[Diffusion Policy]]
  - [[Action Chunking]]
  - [[Consistency Policy]]
  - [[Flow Matching Policy]]
- [[Dexterous Manipulation]]
  - [[In-Hand Manipulation]]
  - [[Tactile Sensing]]
- [[Grasping]]
  - [[6-DoF Grasp Planning]]

## Learning Paradigms
- [[Imitation Learning]]
  - [[Behavior Cloning]]
  - [[DAgger]]
  - [[VLA (Vision-Language-Action)]]
- [[Reinforcement Learning]]
  - [[Sim-to-Real Transfer]]
  - [[Reward Shaping]]
  - [[Domain Randomization]]

## Data & Infrastructure
- [[Teleoperation]]
  - [[Motion Capture]]
  - [[VR Teleoperation]]
- [[Simulation Platforms]]
  - [[Isaac Lab]]
  - [[MuJoCo]]
- [[Hardware Design]]
  - [[Actuator Design]]
  - [[Sensor Integration]]
```

### 2.6 索引维护流程

```
新论文编译完成
      │
      ▼
 ┌─────────────────────────────────────────────┐
 │ 程序自动（build_indexes.py）                  │
 │                                              │
 │ 1. 扫描所有 papers/*.md 的 frontmatter       │
 │ 2. 扫描所有 concepts/*.md 的 frontmatter     │
 │ 3. 重建 papers/INDEX.md 结构（表格骨架）      │
 │ 4. 重建 concepts/INDEX.md 结构               │
 │ 5. 重建 INDEX.md 的 stats + recent           │
 │ 6. 检查 stale raw items                      │
 └──────────────────┬──────────────────────────┘
                    │
                    ▼
 ┌─────────────────────────────────────────────┐
 │ LLM 补充（可选，lint 时触发）                  │
 │                                              │
 │ 1. 为 papers/INDEX.md 中没有摘要的行补写摘要  │
 │ 2. 为 concepts/INDEX.md 中没有描述的行补写    │
 │ 3. 审视 TOPIC-MAP.md，调整层次结构            │
 │ 4. 更新 INDEX.md 的 Topic Overview 表         │
 └──────────────────────────────────────────────┘
```

**程序部分是确定性的**——保证索引不遗漏。
**LLM 部分是增强性的**——提高摘要质量和语义组织。
两者可以独立运行，也可以串联。

### 2.7 Context Budget 估算

LLM 做 Q&A 时的 token 消耗：

| 步骤 | 读什么 | Token 估算 |
|------|--------|-----------|
| 导航 | INDEX.md | ~2K |
| 定位 | papers/INDEX.md 或 concepts/INDEX.md | ~2K-15K |
| 深入 | 2-3 个具体页面 | ~5K-15K |
| **总导航成本** | | **~10K-30K** |
| 剩余给回答 | | **~70K-90K** |

在 Claude 的 200K context 下绰绰有余。即使 wiki 增长到 1000 篇，也只是 papers/INDEX.md 翻倍到 ~40K tokens，仍然可行。

---

## 三、两个系统的交叉点

```
raw_updater        build_indexes        LLM lint
(数据层)           (导航层)             (语义层)
    │                   │                   │
    │ raw 变化          │ frontmatter 变化   │ TOPIC-MAP 调整
    │ stale=true        │                   │
    ▼                   ▼                   ▼
wiki_compiler ──→ 重编译 wiki 页面 ──→ 触发 build_indexes
                  (更新 frontmatter)
```

**解耦的好处：**
- raw_updater 可以独立运行（比如每周检查一次 arXiv 新版本）
- build_indexes 可以独立运行（任何 wiki 页面手动编辑后）
- LLM lint 可以独立运行（定期健康检查）
- 三者也可以串联：daily pipeline → raw_updater → wiki_compiler → build_indexes
