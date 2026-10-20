"""把 DSH 会话记录 (session.v4.jsonl.zstd) 转成可读 Markdown。

用法:
    python make_transcripts.py --out "<pack>\\sessions" [--max-arg 1200] [--max-result 600] [--max-text 4000]

设计目标: 保留"用户说了什么 / agent 调用了什么工具、参数长什么样 / 工具返回了什么(截断)"，
把体积压到可打包的量级。推理(reasoning)内容不导出。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

ZSTD = os.environ.get("NF_ZSTD", r"D:\Anaconda2\Library\bin\zstd.exe")
HOME = os.path.expanduser("~")
SESS_ROOT = os.path.join(HOME, ".dsh", "sessions")

# 打包进来的会话（id -> 人类可读标签）
SELECTED = [
    ("session-8eacd363-ef61-4070-a874-19c2238d93e6", "01-起始-学习native-textbook并为ME4300搭流水线"),
    ("session-d6503ac3-04e8-4b75-92ba-1f58854c7930", "02-把Codex技能接入DSH"),
    ("session-11a87192-edfe-4f71-8832-b49510527e35", "03-从会话zip恢复继续"),
    ("cda35a03-f85b-4910-84d5-58bf755d835c", "04-金融物理-worker起草"),
    ("session-56cd956b-3ae5-4ef6-91ee-1eb571dbeac4", "05-经典力学-主控"),
    ("3a7a4f1f-ea50-47ee-a936-0f171611e999", "06-经典力学-翻译worker"),
    ("session-8baf44b0-3178-4fc9-89a5-b5ef9a55a777", "07-Lecture2-Signals-PPT双版本"),
    ("d5fbdc49-7067-443e-97d3-4bb070ba084d", "08-worker加监工模式"),
    ("session-a7e38e0e-853c-4f3a-89da-0f8b37102b62", "09-native-textbook技能升级"),
    ("session-7f08e267-6926-488e-ac6a-59b05ebd3c2a", "10-计算物理-扫描件主控"),
    ("455ac490-1d58-4186-961e-cc07a2ef9646", "11-计算物理-独立视觉审查"),
    ("session-33a60f0b-3b02-4e63-bba6-3da5024f2c88", "12-失败排查与续跑"),
]


def resolve_path(session_id: str) -> str | None:
    """会话落在 <sessions>/<项目目录>/<会话目录>/session.v4.jsonl.zstd。"""
    for project in os.listdir(SESS_ROOT):
        pdir = os.path.join(SESS_ROOT, project)
        if not os.path.isdir(pdir):
            continue
        for d in os.listdir(pdir):
            if d == session_id or d.endswith(session_id):
                p = os.path.join(pdir, d, "session.v4.jsonl.zstd")
                if os.path.exists(p):
                    return p
    return None


def iter_events(path: str):
    proc = subprocess.Popen([ZSTD, "-d", "-c", "-q", path],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue
    proc.stdout.close()
    proc.wait()


def clip(text: str, limit: int) -> str:
    text = text.replace("\r\n", "\n")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（本段共 {len(text)} 字符，此处截断，仅保留前 {limit} 字符）"


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    out = []
    for part in content or []:
        if isinstance(part, dict) and part.get("type") == "text":
            out.append(part.get("text") or "")
    return "\n".join(out)


def ts(ms):
    if not ms:
        return "?"
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def convert(path: str, label: str, max_arg: int, max_result: int, max_text: int):
    meta = {"id": label, "titles": [], "created": None, "cwd": None,
            "tools": {}, "skills": [], "turns": 0, "first": None, "last": None}
    lines: list[str] = []
    pending_calls = {}
    for ev in iter_events(path):
        t = ev.get("type")
        when = ts(ev.get("time"))
        if when != "?":
            meta["first"] = meta["first"] or when
            meta["last"] = when
        if t == "session":
            meta["id"] = ev.get("id") or label
            meta["created"] = ts(ev.get("createdAt"))
            meta["cwd"] = ev.get("cwd")
        elif t == "session/title":
            title = (ev.get("data") or {}).get("title")
            if title and title not in meta["titles"]:
                meta["titles"].append(title)
        elif t == "turn/start":
            meta["turns"] += 1
            lines.append(f"\n---\n\n## 第 {meta['turns']} 轮（{when}）\n")
        elif t == "user/message":
            data = ev.get("data") or {}
            src = (data.get("source") or {}).get("kind")
            body = text_of(data.get("content"))
            if not body.strip():
                continue
            # 只保留人的输入、子会话/队友消息与完成回执；丢弃运行上下文、技能目录等噪声
            if src == "user":
                lines.append(f"\n### 👤 用户\n\n```text\n{clip(body, max_text)}\n```\n")
            elif src in ("agent-message", "team-message"):
                lines.append(f"\n### 💬 {'子会话' if src == 'agent-message' else '队友'}消息\n\n"
                             f"```text\n{clip(body, 1500)}\n```\n")
            elif src == "subagent-settled":
                first = body.strip().splitlines()[0][:200]
                lines.append(f"\n> ↩ 子会话结束：{first}\n")
            elif src == "goal":
                continue
            elif src in ("runtime-context", "skill-catalog", "tool-jobs",
                         "user-approval", "compact-checkpoint"):
                continue
            else:
                lines.append(f"\n### 👤 用户({src})\n\n```text\n{clip(body, max_text)}\n```\n")
        elif t == "assistant/message":
            msg = ((ev.get("data") or {}).get("message") or {})
            body = text_of(msg.get("content"))
            if body.strip():
                lines.append(f"\n### 🤖 DeepSeek\n\n{clip(body, max_text)}\n")
        elif t == "tool/call":
            data = ev.get("data") or {}
            name = data.get("name")
            args = data.get("arguments")
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            meta["tools"][name] = meta["tools"].get(name, 0) + 1
            if name == "skill":
                try:
                    meta["skills"].append(json.loads(args).get("name"))
                except Exception:
                    pass
            pending_calls[data.get("callId")] = name
            lines.append(f"\n<details><summary>🔧 工具调用 <code>{name}</code></summary>\n\n"
                         f"```json\n{clip(args, max_arg)}\n```\n\n</details>\n")
        elif t == "tool/result":
            data = ev.get("data") or {}
            msg = data.get("message") or {}
            body = text_of(msg.get("content"))
            name = pending_calls.get(data.get("toolCallId"), "?")
            if body.strip():
                lines.append(f"\n<details><summary>📄 返回 <code>{name}</code> "
                             f"({len(body)} 字符)</summary>\n\n```text\n{clip(body, max_result)}\n```\n\n</details>\n")
    head = [
        f"# {label}",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 会话 id | `{meta['id']}` |",
        f"| 会话标题 | {' / '.join(meta['titles']) or '(无)'} |",
        f"| 开始 | {meta['created'] or meta['first']} |",
        f"| 结束 | {meta['last']} |",
        f"| 轮数 | {meta['turns']} |",
        f"| 加载过的 skill | {', '.join([s for s in meta['skills'] if s]) or '(无)'} |",
        f"| 工作目录 | `{meta['cwd']}` |",
        "",
        "**工具调用次数**：" + "、".join(f"`{k}`×{v}" for k, v in
                                   sorted(meta["tools"].items(), key=lambda kv: -kv[1])),
        "",
        "> 本文件由会话原始记录自动转换：只保留用户消息、助手正文、工具调用参数与工具返回（均截断）。",
        "> 推理过程未导出。原文可用同目录 `.jsonl.zstd` 或 DSH 的会话列表重新打开。",
        "",
    ]
    return "\n".join(head) + "\n".join(lines), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-arg", type=int, default=1200)
    ap.add_argument("--max-result", type=int, default=600)
    ap.add_argument("--max-text", type=int, default=4000)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    index = []
    for sid, label in SELECTED:
        path = resolve_path(sid)
        if not path:
            print("MISSING", sid)
            continue
        md, meta = convert(path, label, args.max_arg, args.max_result, args.max_text)
        target = os.path.join(args.out, f"{label}.md")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(md)
        index.append((label, meta, os.path.getsize(target)))
        print(f"{label:44s} {os.path.getsize(target)/1024:8.1f} KB  turns={meta['turns']} "
              f"tools={sum(meta['tools'].values())}")
    with open(os.path.join(args.out, "index.md"), "w", encoding="utf-8") as fh:
        fh.write("# 会话记录索引\n\n以下是本机 DSH 里做「原生中文教材转换」的真实会话，"
                 "由 `session.v4.jsonl.zstd` 自动转换成可读 Markdown。\n\n"
                 "| 文件 | 会话标题 | 开始 | 轮数 | 加载的 skill | 主要工具 |\n|---|---|---|---|---|---|\n")
        for label, meta, size in index:
            tools = "、".join(f"{k}×{v}" for k, v in
                             sorted(meta["tools"].items(), key=lambda kv: -kv[1])[:6])
            fh.write(f"| [{label}]({label}.md) | {' / '.join(meta['titles']) or '-'} | "
                     f"{meta['created']} | {meta['turns']} | "
                     f"{', '.join([s for s in meta['skills'] if s]) or '-'} | {tools} |\n")


if __name__ == "__main__":
    main()
