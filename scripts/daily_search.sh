#!/bin/bash
# Daily paper search script - runs via cron
# Invokes Claude Code CLI with a prompt to search, filter, and push papers

cd /home/gary/Documents/awesome-robot-learning

export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/bin:$PATH"

timeout 30m claude --print -p "You are a daily paper search agent. Follow these steps exactly:

1. Read the topic configurations:
   - Read /home/gary/Documents/research_idea/categories.yaml for the category list
   - Read all topic.yaml files from /home/gary/Documents/research_idea/*/topic.yaml for active research topics and their keywords
   - Read /home/gary/Documents/awesome-robot-learning/feeds.yaml for RSS blog subscriptions
   - Read /home/gary/Documents/awesome-robot-learning/data/taste_profile.yaml for the user's taste profile

2. Search for new papers from the past 2 days:
   Run this command to search arXiv, Semantic Scholar, AND RSS feeds:
   \`\`\`bash
   cd /home/gary/Documents/awesome-robot-learning
   python3 -c \"
import json
from scripts.search_papers import search_arxiv, search_semantic_scholar, build_arxiv_query, build_s2_query, deduplicate, load_seen, save_seen
from scripts.rss_fetcher import fetch_all_feeds
from scripts.config import load_config, load_active_topics, load_feeds
from pathlib import Path

config = load_config()
topics = load_active_topics()
seen_path = Path(config['awesome_repo']['path']) / 'data' / 'seen_papers.json'
seen = load_seen(seen_path)

all_papers = []

# Broad arXiv search
broad_query = build_arxiv_query(['cs.RO', 'cs.AI'])
all_papers.extend(search_arxiv(broad_query, max_results=100, days_back=2))

# Per-topic targeted search
for topic in topics:
    kws = topic.get('keywords', [])
    cats = topic.get('arxiv_categories', ['cs.RO'])
    q = build_arxiv_query(cats, kws)
    all_papers.extend(search_arxiv(q, max_results=50, days_back=2))
    s2q = build_s2_query(kws)
    fields = topic.get('semantic_scholar_fields')
    s2_key = config.get('semantic_scholar', {}).get('api_key', '')
    from datetime import datetime
    all_papers.extend(search_semantic_scholar(s2q, fields, 30, str(datetime.now().year), s2_key))

# RSS feed search
feeds = load_feeds()
rss_papers = fetch_all_feeds(feeds, seen, days_back=7)
all_papers.extend(rss_papers)

unique = deduplicate(all_papers, seen)
print(json.dumps(unique, indent=2, ensure_ascii=False))
\"
   \`\`\`

3. Load the user's taste profile from data/taste_profile.yaml. Use these preferences when filtering:
   - authors_whitelist: papers by these authors are automatically High
   - method_keywords_positive: boost relevance for papers matching these
   - method_keywords_negative: reduce relevance for papers matching these
   - preferences.like: general style preferences
   - preferences.dislike: things to avoid

4. For each paper returned, read the title and abstract. Classify relevance using the taste profile:
   - High: Directly relevant to active research topics AND matches taste preferences
   - Medium: Related to robot learning broadly, partially matches preferences
   - Low: Not relevant or matches dislike criteria - skip
   Papers by whitelist authors are automatically High.

5. For High papers, use the /collect-paper skill to collect them (Zotero + Notion + Git).
   When writing to Notion, include:
   - method_summary: 中文，包含方法核心思想、关键创新点、实验结论
   - recommendation_reason: 中文，说明为什么推荐这篇（和哪个研究方向相关、是否是关注作者的新作等）
   - source: 'arXiv' for papers, 'RSS' for blog posts

6. Send a Feishu message to chat_id 'oc_30b09432428ad657a14f92be4e725ab2' with all High and Medium papers.
   Use this EXACT format (all content in Chinese):

   📬 今日论文推荐（YYYY-MM-DD）

   ⭐ 高相关

   [Category] Paper Title
   方法：2-3句中文描述方法核心思想和关键创新点
   推荐理由：中文说明为什么推荐（匹配的研究方向、关注的作者、方法特点等）
   链接：url | 项目：project_url（如有）
   状态：已收录至 Zotero + Notion + Git

   📎 可能感兴趣

   Paper Title — 一句话中文摘要
   链接：url

   📡 博客更新（if any RSS entries found）

   [Source Name] Blog Post Title
   摘要：中文摘要
   链接：url
   推荐理由：中文说明为什么推荐

   If no papers found, send: '📬 今日无新相关论文。'

7. Update seen_papers.json with all processed paper IDs (including RSS entries with rss: prefix):
   \`\`\`bash
   cd /home/gary/Documents/awesome-robot-learning
   python3 -c \"
import json
from scripts.search_papers import load_seen, save_seen
from pathlib import Path
from datetime import date
seen_path = Path('/home/gary/Documents/awesome-robot-learning/data/seen_papers.json')
seen = load_seen(seen_path)
# new_entries will be provided as needed
save_seen(seen_path, seen)
\"
   \`\`\`

8. Commit and push any changes to seen_papers.json and README.md.
" >> /home/gary/Documents/awesome-robot-learning/logs/daily_search_$(date +%Y%m%d).log 2>&1
