#!/usr/bin/env python3
"""
解析 GitHub Issue Form 表單主體，產出 feature_list.json 新項目。

GitHub Issue Forms 的 body 格式（每個欄位前有 ### 標頭）：
  ### Category
  
  functional
  
  ### Description
  
  Add rate limiting to all API endpoints
  
  ### Verification Steps
  
  Step 1: Start the API service
  Step 2: Verify response is 429

輸出：
  - 更新 feature_list.json（追加新項目）
  - 寫 NEW_INDEX=N 到 $GITHUB_OUTPUT
"""

import json
import os
import re
import sys
from pathlib import Path


def parse_issue_body(body: str) -> dict:
    """將 GitHub Issue Form 的 body 解析成結構化欄位。"""
    sections: dict[str, str] = {}
    current_header = None
    buffer_lines: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()
        # GitHub Issue Forms 用 ### 標示欄位名稱
        if line.startswith("### "):
            if current_header is not None:
                sections[current_header] = "\n".join(buffer_lines).strip()
            current_header = line[4:].strip()
            buffer_lines = []
        elif current_header is not None:
            buffer_lines.append(raw_line)

    # 最後一個段落
    if current_header is not None:
        sections[current_header] = "\n".join(buffer_lines).strip()

    return sections


def extract_steps(steps_text: str) -> list[str]:
    """從步驟文字中提取每一步（過濾空行）。"""
    steps = []
    for line in steps_text.splitlines():
        line = line.strip()
        # 接受 "Step N: ..." 或任何非空行
        if line:
            steps.append(line)
    return steps


def main() -> None:
    # 讀取 GitHub Actions 事件 JSON
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("錯誤：GITHUB_EVENT_PATH 未設定", file=sys.stderr)
        sys.exit(1)

    with open(event_path, encoding="utf-8") as f:
        event = json.load(f)

    issue = event.get("issue", {})
    body = issue.get("body", "")
    issue_number = issue.get("number", 0)

    if not body:
        print("錯誤：Issue body 為空", file=sys.stderr)
        sys.exit(1)

    sections = parse_issue_body(body)

    # 提取必要欄位（欄位名稱與 ISSUE_TEMPLATE 的 label 對應）
    category = sections.get("Category", "functional").strip().lower()
    description = sections.get("Description", "").strip()
    steps_text = sections.get("Verification Steps", "").strip()

    if not description:
        print("錯誤：Description 欄位為空", file=sys.stderr)
        sys.exit(1)

    steps = extract_steps(steps_text)
    if not steps:
        # 至少給一個預設步驟，避免空 list
        steps = [f"Step 1: Verify feature from issue #{issue_number} works correctly"]

    # 讀取現有 feature_list.json
    repo_root = Path(__file__).parent.parent
    feature_list_path = repo_root / "feature_list.json"

    if feature_list_path.exists():
        with open(feature_list_path, encoding="utf-8") as f:
            feature_list = json.load(f)
    else:
        feature_list = []

    new_index = len(feature_list)  # 0-based index，即第 N+1 個 feature

    # 建立新項目
    new_entry = {
        "category": category,
        "description": description,
        "steps": steps,
        "passes": False,
    }

    feature_list.append(new_entry)

    # 寫回 feature_list.json
    with open(feature_list_path, "w", encoding="utf-8") as f:
        json.dump(feature_list, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"✅ 新增 feature #{new_index + 1}（index {new_index}）: {description}")
    print(f"   category: {category}, steps: {len(steps)} 步")

    # 寫 GitHub Actions output 變數
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"NEW_INDEX={new_index}\n")
            f.write(f"FEATURE_DESC={description}\n")
    else:
        # 本機測試時印出
        print(f"NEW_INDEX={new_index}")
        print(f"FEATURE_DESC={description}")


if __name__ == "__main__":
    main()
