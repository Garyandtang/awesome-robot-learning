#!/bin/bash
# Daily paper search script - runs via cron
# Invokes Claude Code CLI with a prompt to search, filter, and push papers

cd /home/gary/Documents/awesome-robot-learning

export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/bin:$PATH"

timeout 30m claude --print -p "You are a daily paper search agent. Follow these steps exactly:

1. Read the topic configurations:
   - Read /home/gary/Documents/research_idea/categories.yaml for the category list
   - Read all topic.yaml files from /home/gary/Documents/research_idea/*/topic.yaml for active research topics and their keywords

2. Search for new papers from the past 2 days:
   Run this command to search arXiv and Semantic Scholar:
   \`\`\`bash
   cd /home/gary/Documents/awesome-robot-learning
   python3 -c \"
import json
from scripts.search_papers import search_arxiv, search_semantic_scholar, build_arxiv_query, build_s2_query, deduplicate, load_seen, save_seen
from scripts.config import load_config, load_active_topics
from pathlib import Path

config = load_config()
topics = load_active_topics()
seen_path = Path(config['awesome_repo']['path']) / 'data' / 'seen_papers.json'
seen = load_seen(seen_path)

all_papers = []

# Broad search
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

unique = deduplicate(all_papers, seen)
print(json.dumps(unique, indent=2, ensure_ascii=False))
\"
   \`\`\`

3. For each paper returned, read the title and abstract. Classify relevance:
   - High: Directly relevant to one of the active research topics (manipulation, loco-manipulation, VLA, force control, sim-to-real)
   - Medium: Related to robot learning broadly but not a direct match
   - Low: Not relevant - skip

4. For High papers, use the /collect-paper skill to collect them (Zotero + Notion + Git).

5. Send a Feishu message to chat_id 'oc_30b09432428ad657a14f92be4e725ab2' with all High and Medium papers:

   High papers format:
   [High] Category
   Paper Title
   Method: 2-sentence summary
   Topics: associated topics
   Link: url
   Status: Collected to Zotero + Notion + Git

   Medium papers format:
   [Medium]
   Paper Title — one-line summary
   Link: url

   If no papers found, send: 'No new relevant papers found today.'

6. Update seen_papers.json with all processed paper IDs:
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

7. Commit and push any changes to seen_papers.json and README.md.
" >> /home/gary/Documents/awesome-robot-learning/logs/daily_search_$(date +%Y%m%d).log 2>&1
