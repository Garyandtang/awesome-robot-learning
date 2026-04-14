# Awesome Robot Learning —— 个人研究助理系统

这不是一份普通的论文 awesome-list，而是一套为**机器人学习研究**设计的**自动化研究管道 + LLM 外置记忆**，把"每天爬新论文 → 按口味筛 → 抽取正文 → LLM 编译进知识库"这条链路跑通。

核心理念（借鉴 Andrej Karpathy）：**LLM 是无状态的，所以把思考的结果写成结构化 wiki，让它下次能接着用。**

---

## 能做什么

| 场景 | 命令 / 入口 |
|------|------------|
| 每天自动推送今日机器人论文到邮箱/Notion | `scripts/daily_search.sh`（配合 cron） |
| 按个人口味三级打分（L1 规则 → L2 向量 → L3 LLM） | `scripts/taste_engine.py` |
| 把一篇论文抓成 raw 素材（PDF 正文 + 图 + 公式 + repo README） | `python -m scripts.raw_ingest <arxiv_id>` |
| LLM 编译成中文 wiki 页（含跨论文 concept 合成） | `python -m scripts.wiki_compiler <arxiv_id>` |
| 把一个开源代码仓库纳入知识库（meta + README + 目录树） | `python -m scripts.codebase_ingest <slug> <url>` |
| 重建 wiki 索引 | `python -m scripts.index_builder` |

---

## 目录结构

```
awesome-robot-learning/           ← 公开仓库
├── README.md                      本文件
├── scripts/                       研究管道的所有 Python 逻辑
├── data/                          taste profile、embedding 缓存
├── feeds.yaml                     RSS 订阅
├── tests/                         pytest
└── wiki/ (submodule, private)    ← 外置记忆，指向 awesome-robot-learning-wiki
    ├── INDEX.md                   全局入口
    ├── TOPIC-MAP.md               研究话题拓扑
    ├── papers/{arxiv_id}.md       单篇深度分析（中文）
    ├── concepts/{slug}.md         跨论文概念合成
    ├── codebase/{slug}.md         代码库合成页
    └── raw/                       原料层（LLM 编译的输入）
        ├── papers/{id}/           meta.yaml + fulltext.md + images/ + repo-readme.md
        └── codebases/{slug}/      meta.yaml + readme.md + tree.txt + src/(gitignored)
```

**为什么 wiki 是 submodule**：wiki 是个人研究笔记，涉及未发表想法和第三方代码摘录，适合放**私有** repo；awesome-list 的公开 repo 保持小巧干净，只留一个 submodule 指针。

---

## 安装

### 1. 克隆（带 submodule）

```bash
git clone --recurse-submodules git@github.com:Garyandtang/awesome-robot-learning.git
cd awesome-robot-learning
```

如果 wiki submodule 是私有的，别人没权限时 submodule 会 skip —— 主仓库仍可用。

### 2. Conda 环境

```bash
conda create -n paper-rec python=3.11 -y
conda activate paper-rec
pip install -r requirements.txt
```

额外依赖：
- `marker-pdf`（PDF → Markdown with inline LaTeX，Marker fulltext 抽取）
- `pymupdf`（图片抽取，已在 requirements.txt）

### 3. 配置文件

在 `~/.config/paper-collector/config.yaml` 写：

```yaml
awesome_repo:
  path: /path/to/awesome-robot-learning
research_idea:
  path: /path/to/awesome-robot-learning
wiki:
  path: /path/to/awesome-robot-learning/wiki

# 可选
zotero:
  api_key: xxx
  library_id: xxx
notion:
  token: xxx
  database_id: xxx
openai:
  api_key: xxx   # 或 anthropic.api_key
```

---

## 常见工作流

### A. 手动收录一篇论文到 wiki

```bash
# 1. 抓 raw 原料（arXiv metadata + Marker 抽正文 + 抽图 + 抓 repo README）
python -m scripts.raw_ingest 2503.02881

# 2. LLM 编译成中文 wiki 页（两步调用）
python -c "from scripts.wiki_compiler import compile_paper_v2; compile_paper_v2('2503.02881')"

# 3. 重建索引
python -c "from scripts.index_builder import build_all_indexes; build_all_indexes()"

# 4. 提交到 wiki 子模块
cd wiki && git add . && git commit -m "add 2503.02881" && git push && cd ..
git add wiki && git commit -m "bump wiki" && git push
```

### B. 纳入一个代码库

```bash
python -m scripts.codebase_ingest reactive-diffusion-policy \
    https://github.com/xiaoxiaoxh/reactive_diffusion_policy \
    --description "RDP：slow-fast 非对称 tokenizer + reactive imitation"
```

产出 `wiki/raw/codebases/{slug}/` 下的 `meta.yaml + readme.md + tree.txt + src/`（src/ 是完整 clone，gitignored）。

### C. 日常推荐（cron）

```bash
# 编辑 crontab，每天早上跑
0 9 * * * /bin/bash /path/to/scripts/daily_search.sh
```

`daily_pipeline.py` 会：
1. 从 arXiv + Semantic Scholar + RSS 拉当日候选
2. 三级漏斗打分（taste_engine）
3. 命中的论文写到 Zotero/Notion/本地 README
4. 高分论文可选自动 raw ingest

### D. 研究问答（使用 wiki）

直接把 `wiki/INDEX.md` 作为 LLM 会话的起点。导航协议：

```
wiki/INDEX.md               → 看全局统计 + 最近 7 天
wiki/TOPIC-MAP.md           → 定位话题
wiki/concepts/INDEX.md      → 按字母序找 concept
wiki/concepts/{slug}.md     → 读跨论文合成
wiki/papers/{arxiv_id}.md   → 下钻单篇细节
wiki/raw/papers/{id}/       → 原始 metadata / fulltext
```

---

## 运行测试

```bash
conda activate paper-rec
python3 -m pytest tests/ -v --override-ini="addopts=" -p no:cacheprovider
```

两个标志是为了避开系统里 ROS 的 pytest 插件。

---

## 设计理念

- **代码做确定性的事**（抓 PDF、抽图、建索引、打分漏斗），**LLM 做语义的事**（读懂论文、抽 concept、跨论文合成）。
- **Raw 层和 wiki 层分离**：raw 层是 LLM 编译器的输入原料（meta + fulltext + 图），wiki 层是 LLM 的输出成品（papers/ concepts/）。重新编译时不需要重新抓 PDF。
- **Commit SHA 钉死代码版本**：`codebases/{slug}/meta.yaml` 记录 clone 时的 commit，重现性靠这个。
- **Wiki 是知识资产**，不是缓存 —— 所以单独一个 private repo 做版本化，图片这类可重建的大文件则 gitignore 掉（Marker + PyMuPDF 随时能重抽）。

---

## 过去的论文 awesome-list？

以前的版本是一份按任务分类的机器人学习论文列表（Manipulation / VLA / Force Control / Sim-to-Real / ...）。那份数据现在由 `scripts/daily_pipeline` 自动写入、由 wiki 做深度合成，不再作为 README 的主体展示。

如果需要复古形式的"扁平论文列表"，可以从 git 历史 `git log --follow README.md` 里找到旧版本。

---

## License

MIT（代码）。Wiki 内容包含论文摘录与分析笔记，遵循各原论文的 license。
