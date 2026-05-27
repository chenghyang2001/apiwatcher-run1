#!/bin/bash
set -euo pipefail
# ==============================================================================
# run_feature_loop.sh — apiwatcher-run1 自主功能實作迴圈
#
# 由 GitHub Actions (issue-to-feature.yml) 透過 SSH 觸發，在 VPS 背景執行。
# 使用 Claude CLI coding 迴圈實作 feature_list.json 中 passes:false 的項目。
#
# 用法：bash scripts/run_feature_loop.sh BRANCH ISSUE_NUM PR_NUM [FEATURE_INDEX]
#
# 必要環境變數（在 ~/.vps-secrets 設定，或由 caller 傳入）：
#   ANTHROPIC_API_KEY  — Claude API key
#   GH_PAT             — GitHub Personal Access Token（repo scope）
#
# ~/.vps-secrets 範本：
#   export ANTHROPIC_API_KEY="sk-ant-..."
#   export GH_PAT="ghp_..."
# ==============================================================================

BRANCH="${1:?用法：$0 BRANCH ISSUE_NUM PR_NUM [FEATURE_INDEX]}"
ISSUE_NUM="${2:?用法：$0 BRANCH ISSUE_NUM PR_NUM [FEATURE_INDEX]}"
PR_NUM="${3:?用法：$0 BRANCH ISSUE_NUM PR_NUM [FEATURE_INDEX]}"
FEATURE_INDEX="${4:-null}"   # 可選，傳入 dispatch payload 供 Workflow 2 使用

# --- VPS 路徑 -----------------------------------------------------------------
AUTONOMOUS_LOOP_DIR="/home/claude/workspace/anthropic-quickstarts/autonomous-coding-linux"
PROJECT_DIR="${AUTONOMOUS_LOOP_DIR}/generations/apiwatcher_run1"
CODING_PROMPT="${AUTONOMOUS_LOOP_DIR}/prompts/coding_prompt.md"
PARSER_PATH="${AUTONOMOUS_LOOP_DIR}/scripts/parse_claude_stream.py"
GH_REPO="chenghyang2001/apiwatcher-run1"

# --- 載入 VPS secrets（若環境變數尚未設定）-----------------------------------
SECRETS_FILE="${HOME}/.vps-secrets"
if [ -f "$SECRETS_FILE" ]; then
  # shellcheck disable=SC1090
  source "$SECRETS_FILE"
fi

# 環境變數必要性檢查
for var in ANTHROPIC_API_KEY GH_PAT; do
  val="${!var:-}"
  if [ -z "$val" ]; then
    echo "錯誤：缺少環境變數 ${var}。" >&2
    echo "      請在 ~/.vps-secrets 中設定或由 caller 傳入。" >&2
    exit 1
  fi
done

# --- 可調整參數 ---------------------------------------------------------------
MAX_ITER="${MAX_ITER:-10}"          # coding 迴圈最大迭代數
STALL_LIMIT="${STALL_LIMIT:-3}"     # 連續無進度圈數上限（止血）
SLEEP_INTERVAL="${SLEEP_INTERVAL:-5}" # 兩 session 之間的間隔秒數
MODEL="${MODEL:-claude-sonnet-4-5-20250929}"

echo "=== apiwatcher-run1 Feature Loop 啟動 ==="
echo "  Branch:        $BRANCH"
echo "  Issue:         #$ISSUE_NUM"
echo "  PR:            #$PR_NUM"
echo "  Feature Index: $FEATURE_INDEX"
echo "  Model:         $MODEL"
echo "  Max Iter:      $MAX_ITER"
echo "  Start Time:    $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================"

# --- 切換到 feature branch ---------------------------------------------------
cd "$PROJECT_DIR"
git fetch origin

# 若 branch 已存在（本地或遠端）就 checkout；否則從 origin 建立
if git checkout "$BRANCH" 2>/dev/null; then
  git pull origin "$BRANCH" || true
elif git checkout -b "$BRANCH" "origin/$BRANCH" 2>/dev/null; then
  : # 已從遠端建立
else
  echo "錯誤：找不到 branch $BRANCH（本地或遠端）" >&2
  exit 1
fi

# --- 確保 .claude/settings.json 存在（允許 bypassPermissions）---------------
mkdir -p "$PROJECT_DIR/.claude"
cat > "$PROJECT_DIR/.claude/settings.json" << 'SETTINGS_EOF'
{
  "permissions": {
    "defaultMode": "bypassPermissions",
    "allow": [
      "Read", "Write", "Edit", "Glob", "Grep",
      "Bash(npm:*)", "Bash(node:*)",
      "Bash(git add:*)", "Bash(git commit:*)", "Bash(git status:*)",
      "Bash(git diff:*)", "Bash(git log:*)", "Bash(git push:*)",
      "Bash(ls:*)", "Bash(cat:*)", "Bash(mkdir:*)",
      "Bash(cp:*)", "Bash(mv:*)", "Bash(rm:*)", "Bash(touch:*)",
      "Bash(curl:*)", "Bash(python3:*)", "Bash(pip3:*)",
      "Bash(bash:*)", "Bash(sh:*)", "Bash(chmod:*)",
      "Bash(grep:*)", "Bash(find:*)", "Bash(echo:*)",
      "Bash(ps:*)", "Bash(kill:*)", "Bash(pkill:*)",
      "Bash(ss:*)", "Bash(lsof:*)", "Bash(sleep:*)",
      "Bash(date:*)", "Bash(env:*)", "Bash(export:*)",
      "Bash(sed:*)", "Bash(awk:*)", "Bash(wc:*)"
    ]
  }
}
SETTINGS_EOF

# --- 計算剩餘 feature 數 -----------------------------------------------------
count_remaining() {
  python3 -c "
import json
fl = json.load(open('feature_list.json', encoding='utf-8'))
print(sum(1 for f in fl if not f.get('passes', False)))
"
}

# --- Coding 迴圈（跳過 initializer，feature_list.json 已由 CI 更新）---------
prev_remaining=-1
stall_count=0
loop_exit_code=0

for i in $(seq 1 "$MAX_ITER"); do
  if remaining="$(count_remaining 2>/dev/null)"; then
    :
  else
    echo "錯誤：無法解析 feature_list.json" >&2
    loop_exit_code=1
    break
  fi

  if [ "$remaining" -eq 0 ]; then
    echo "✅ 全部 feature 通過，迴圈完成"
    break
  fi

  # Stall detection：連續無進度超過上限則中止
  if [ "$prev_remaining" -ne -1 ] && [ "$remaining" -ge "$prev_remaining" ]; then
    stall_count=$((stall_count + 1))
    echo "⚠️  第 $i 圈無進度（remaining=$remaining），連續 $stall_count/$STALL_LIMIT 圈" >&2
  else
    stall_count=0
  fi
  if [ "$stall_count" -ge "$STALL_LIMIT" ]; then
    echo "⚠️  連續 $STALL_LIMIT 圈無進度，提前中止以節省成本。剩餘 $remaining 個 feature" >&2
    break
  fi
  prev_remaining="$remaining"

  echo ""
  echo "--- Session $((i+1)): coding（第 $i/$MAX_ITER 圈，剩餘 $remaining，$(date -u '+%H:%M:%SZ')）---"

  TMPOUT=$(mktemp /tmp/loop_${ISSUE_NUM}_XXXX.jsonl)
  DISABLE_WRITER_QA_HOOK=1 claude -p "Continue. Execute your coding task now." \
    --system-prompt-file "$CODING_PROMPT" \
    --model "$MODEL" \
    --permission-mode bypassPermissions \
    --max-turns 200 \
    --output-format stream-json \
    --verbose \
    >> "$TMPOUT" &
  CPID=$!

  set +e
  python3 "$PARSER_PATH" "$TMPOUT"
  PEXIT=$?
  set -e

  kill "$CPID" 2>/dev/null || true
  wait "$CPID" 2>/dev/null || true
  rm -f "$TMPOUT"

  if [ $PEXIT -ne 0 ]; then
    echo "錯誤：第 $i 圈 coding session 非零退出（rate limit / timeout / auth 過期）" >&2
    loop_exit_code=1
    break
  fi

  sleep "$SLEEP_INTERVAL"
done

# --- Git commit + push（即使未全數通過也 push 中間進度）---------------------
echo ""
echo "--- Git: commit + push ---"
git add -A
if ! git diff --cached --quiet; then
  git commit -m "feat: implement feature from issue #${ISSUE_NUM} [autonomous-ci]"
  git push origin "$BRANCH"
  echo "✅ 已推送到 $BRANCH"
else
  echo "ℹ️  無新的 git 變更"
fi

# --- 計算最終狀態 -------------------------------------------------------------
final_remaining="$(count_remaining 2>/dev/null || echo 'unknown')"
echo ""
echo "=== 迴圈結束 ==="
echo "  最終剩餘 feature 數: $final_remaining"
echo "  Exit code: $loop_exit_code"
echo "  End Time: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# --- Dispatch Workflow 2 (verify-and-merge.yml) ------------------------------
echo ""
echo "--- GitHub: 通知 Workflow 2 ---"

curl -sf -X POST \
  -H "Authorization: token ${GH_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GH_REPO}/dispatches" \
  -d "{
    \"event_type\": \"vps-coding-complete\",
    \"client_payload\": {
      \"branch\": \"${BRANCH}\",
      \"issue\": ${ISSUE_NUM},
      \"pr\": ${PR_NUM},
      \"feature_index\": ${FEATURE_INDEX},
      \"remaining\": \"${final_remaining}\",
      \"exit_code\": ${loop_exit_code}
    }
  }"

echo "✅ GitHub dispatch 已送出 → verify-and-merge.yml 將開始驗證"
