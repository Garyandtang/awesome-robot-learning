#!/bin/bash
# Daily paper search + recommendation pipeline
# Runs via cron, uses Python taste engine for recommendation

cd /home/gary/Documents/awesome-robot-learning

export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/bin:$PATH"

# Activate conda environment
eval "$(conda shell.bash hook)"
conda activate paper-rec

LOG_FILE="/home/gary/Documents/awesome-robot-learning/logs/daily_search_$(date +%Y%m%d).log"

echo "$(date): Starting pipeline (python: $(which python3))" >> "$LOG_FILE"

# Step 1: Run the taste engine pipeline (search + filter + score)
PIPELINE_OUTPUT=$(timeout 25m python3 -c "
import json
from scripts.daily_pipeline import run_daily_pipeline
result = run_daily_pipeline()
print(json.dumps(result, ensure_ascii=False))
" 2>> "$LOG_FILE")

if [ $? -ne 0 ]; then
    echo "$(date): Pipeline failed" >> "$LOG_FILE"
    exit 1
fi

echo "$(date): Pipeline output: $PIPELINE_OUTPUT" >> "$LOG_FILE"

# Step 2: Send Feishu message via claude --print
MESSAGE=$(echo "$PIPELINE_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('message', '📬 今日无新相关论文。'))
")

timeout 5m claude --print --allowedTools "mcp__feishu__im_v1_message_create" -p "发送以下消息到飞书群 chat_id 'oc_30b09432428ad657a14f92be4e725ab2':

$MESSAGE" >> "$LOG_FILE" 2>&1

# Step 3: Commit seen_papers.json changes
if git diff --quiet data/seen_papers.json 2>/dev/null; then
    echo "$(date): No changes to seen_papers.json" >> "$LOG_FILE"
else
    git add data/seen_papers.json
    git commit -m "chore: update seen_papers.json $(date +%Y-%m-%d)"
    git push
    echo "$(date): Committed and pushed seen_papers.json" >> "$LOG_FILE"
fi
