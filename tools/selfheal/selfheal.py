#!/usr/bin/env python3
"""
selfheal - read deployed error logs from Render, group them into distinct issues,
and (for the ones you pick) run a coding agent on an isolated branch and open a PR.

Stdlib only. Run from the repo with uv:

    export RENDER_API_KEY=rnd_xxx
    uv run tools/selfheal/selfheal.py setup
    uv run tools/selfheal/selfheal.py logs --since 6h
    uv run tools/selfheal/selfheal.py run --since 6h

See tools/selfheal/README.md for what you need to connect.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

RENDER_API_BASE = "https://api.render.com/v1"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_env_file():
    """把仓库根目录 .env（或当前目录 .env）中的变量载入 os.environ。
    不覆盖已存在的 shell 变量，因此显式 export 优先。"""
    for path in (os.path.join(REPO_ROOT, ".env"), os.path.join(os.getcwd(), ".env")):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass

# 各 agent CLI 的调用方式（argv 模板，{prompt} 会被替换为完整提示词）
# 注意：codex exec 会在检测到 stdin 被重定向（非 TTY）时尝试读取额外输入直到 EOF，
# 即使已提供 prompt 参数；run_agent() 会显式把 stdin 接到 /dev/null 避免挂起。
# --full-auto 已废弃，现用 -s workspace-write。
AGENTS = {
    "codex": ["codex", "exec", "-s", "workspace-write", "{prompt}"],
    "cursor": ["cursor-agent", "-p", "{prompt}"],
}


# --------------------------------------------------------------------------- #
# 输出小工具
# --------------------------------------------------------------------------- #
def _c(code: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(t):
    return _c("1", t)


def dim(t):
    return _c("2", t)


def red(t):
    return _c("31", t)


def green(t):
    return _c("32", t)


def yellow(t):
    return _c("33", t)


def cyan(t):
    return _c("36", t)


def die(msg: str, code: int = 1):
    print(red(f"error: {msg}"), file=sys.stderr)
    sys.exit(code)


def info(msg: str):
    print(cyan("• ") + msg)


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print(green(f"saved {CONFIG_PATH}"))


def require_api_key() -> str:
    key = os.environ.get("RENDER_API_KEY", "").strip()
    if not key:
        die("RENDER_API_KEY is not set. Create one at Render Dashboard -> Account "
            "Settings -> API Keys, then: export RENDER_API_KEY=rnd_xxx")
    return key


# --------------------------------------------------------------------------- #
# Render API
# --------------------------------------------------------------------------- #
def render_get(path: str, params: dict | None = None):
    key = require_api_key()
    url = f"{RENDER_API_BASE}{path}"
    if params:
        # 支持重复 key（Render 用 ?type=app&type=build 这种多值形式）
        pairs = []
        for k, v in params.items():
            if isinstance(v, (list, tuple)):
                pairs.extend((k, str(x)) for x in v)
            elif v is not None:
                pairs.append((k, str(v)))
        url += "?" + urllib.parse.urlencode(pairs)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        if e.code == 401:
            die("Render API returned 401 - check RENDER_API_KEY.")
        if e.code == 404:
            die(f"Render API 404 for {path} - check the service/owner id. {body}")
        die(f"Render API {e.code} for {path}: {body}")
    except urllib.error.URLError as e:
        die(f"cannot reach Render API: {e}")


def list_services() -> list[dict]:
    # /v1/services 返回 [{ service: {...}, cursor: ... }]
    out = render_get("/services", {"limit": 100})
    services = []
    for item in out or []:
        svc = item.get("service") if isinstance(item, dict) else None
        if svc:
            services.append(svc)
    return services


def parse_since(since: str) -> str:
    """把 '6h' / '30m' / '2d' 转成 ISO8601 起始时间。"""
    m = re.fullmatch(r"(\d+)\s*([smhd])", since.strip().lower())
    if not m:
        die("--since must look like 30m, 6h, or 2d")
    n, unit = int(m.group(1)), m.group(2)
    delta = {"s": timedelta(seconds=n), "m": timedelta(minutes=n),
             "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]
    return (datetime.now(timezone.utc) - delta).replace(microsecond=0).isoformat()


def fetch_logs(cfg: dict, since: str, levels: list[str], types: list[str],
               max_pages: int = 10) -> list[dict]:
    owner_id = cfg.get("ownerId")
    service_id = cfg.get("serviceId")
    if not owner_id or not service_id:
        die("no service configured - run: selfheal.py setup")

    start_time = parse_since(since)
    logs: list[dict] = []
    params = {
        "ownerId": owner_id,
        "resource": [service_id],
        "type": types,
        "level": levels,
        "startTime": start_time,
        "limit": 100,
        "direction": "backward",
    }
    for _ in range(max_pages):
        out = render_get("/logs", params)
        batch = (out or {}).get("logs", [])
        logs.extend(batch)
        if not (out or {}).get("hasMore"):
            break
        next_start = (out or {}).get("nextStartTime")
        next_end = (out or {}).get("nextEndTime")
        if not next_end:
            break
        # 继续向更早的时间翻页
        params = dict(params)
        params["endTime"] = next_end
        if next_start:
            params["startTime"] = next_start
    return logs


# --------------------------------------------------------------------------- #
# 错误分组
# --------------------------------------------------------------------------- #
_TRACE_START = "Traceback (most recent call last):"
_EXC_LINE = re.compile(r"^(?:[A-Za-z_][\w.]*(?:Error|Exception|Warning))\b.*")
_FRAME_FILE = re.compile(r'File "([^"]+)", line (\d+)')


def _msg_of(entry: dict) -> str:
    if isinstance(entry, dict):
        return str(entry.get("message", "")).rstrip("\n")
    return str(entry)


def _ts_of(entry: dict) -> str:
    if isinstance(entry, dict):
        return str(entry.get("timestamp", ""))
    return ""


def normalize_signature(msg: str) -> str:
    """把日志里易变的部分抹掉，方便聚合相同错误。"""
    s = msg
    s = re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?", "<ts>", s)
    s = re.sub(r"\bproj_[0-9a-f]+\b", "<proj>", s)
    s = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<uuid>", s)
    s = re.sub(r"0x[0-9a-fA-F]+", "<addr>", s)
    s = re.sub(r"\b\d+\b", "<n>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:200]


def group_errors(logs: list[dict]) -> list[dict]:
    """
    将日志聚合为若干"问题"。会把多行 Python traceback 拼接为一条。
    返回按出现次数排序的问题列表：{signature, count, last_seen, excerpt}
    """
    # Render 是 backward（新->旧），先转成时间正序方便拼接 traceback
    entries = list(reversed(logs))
    groups: dict[str, dict] = {}

    def add(signature: str, excerpt: str, ts: str):
        g = groups.get(signature)
        if g is None:
            groups[signature] = {
                "signature": signature,
                "count": 1,
                "last_seen": ts,
                "excerpt": excerpt.strip(),
            }
        else:
            g["count"] += 1
            if ts and ts > g["last_seen"]:
                g["last_seen"] = ts
                g["excerpt"] = excerpt.strip()  # 保留最近一次的样本

    i = 0
    n = len(entries)
    while i < n:
        msg = _msg_of(entries[i])
        ts = _ts_of(entries[i])
        if _TRACE_START in msg:
            # 收集到异常终止行为止
            block = [msg]
            j = i + 1
            exc_line = None
            while j < n and j - i < 200:
                lmsg = _msg_of(entries[j])
                block.append(lmsg)
                if _EXC_LINE.match(lmsg.strip()):
                    exc_line = lmsg.strip()
                    break
                j += 1
            # 签名 = 异常行 + 最深的应用代码帧
            frames = _FRAME_FILE.findall("\n".join(block))
            app_frames = [f for f in frames if "site-packages" not in f[0] and ".venv" not in f[0]]
            loc = ""
            if app_frames:
                fp, ln = app_frames[-1]
                loc = f" @ {os.path.basename(fp)}:{ln}"
            elif frames:
                fp, ln = frames[-1]
                loc = f" @ {os.path.basename(fp)}:{ln}"
            sig = ((exc_line or "Traceback") + loc)[:200]
            add(sig, "\n".join(block[-40:]), ts)
            i = j + 1
            continue

        # 非 traceback：按归一化后的消息聚合（忽略空行）
        if msg.strip():
            add(normalize_signature(msg), msg, ts)
        i += 1

    result = sorted(groups.values(), key=lambda g: g["count"], reverse=True)
    return result


# --------------------------------------------------------------------------- #
# git / gh 辅助
# --------------------------------------------------------------------------- #
def run(cmd: list[str], check=True, capture=False, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, check=check, cwd=cwd,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )


def git(*args, capture=True, check=True) -> str:
    cp = run(["git", *args], check=check, capture=capture)
    return (cp.stdout or "").strip() if capture else ""


def ensure_clean_tree():
    status = git("status", "--porcelain")
    if status:
        die("working tree is not clean. Commit/stash your changes first:\n" + status)


def default_branch() -> str:
    # origin/HEAD -> origin/main 之类
    try:
        ref = git("symbolic-ref", "refs/remotes/origin/HEAD", check=False)
        if ref:
            return ref.rsplit("/", 1)[-1]
    except Exception:
        pass
    for b in ("main", "master"):
        if git("branch", "--list", b):
            return b
    return git("rev-parse", "--abbrev-ref", "HEAD")


def slugify(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (s or "issue")[:maxlen].strip("-")


# --------------------------------------------------------------------------- #
# agent
# --------------------------------------------------------------------------- #
def detect_agent(preferred: str | None = None) -> str | None:
    import shutil
    order = [preferred] if preferred else []
    order += ["codex", "cursor"]
    for name in order:
        if not name:
            continue
        binary = AGENTS[name][0]
        if shutil.which(binary):
            return name
    return None


def build_prompt(issue: dict) -> str:
    return (
        "You are fixing a production error in this repository.\n\n"
        f"Error signature:\n{issue['signature']}\n\n"
        f"Occurrences: {issue['count']} (last seen {issue['last_seen']})\n\n"
        "Raw log excerpt:\n"
        "-----\n"
        f"{issue['excerpt']}\n"
        "-----\n\n"
        "Task: find the root cause in the codebase and apply a minimal, targeted fix. "
        "Do not refactor or touch unrelated code. Do not add dependencies unless strictly "
        "required. When done, briefly summarize what you changed and why."
    )


def run_agent(agent: str, prompt: str) -> int:
    template = AGENTS[agent]
    argv = [prompt if part == "{prompt}" else part for part in template]
    info(f"running agent: {' '.join(argv[:-1])} <prompt>")
    # stdin must be closed/redirected: some agent CLIs (e.g. codex exec) detect a
    # non-TTY stdin and block reading extra input until EOF even when a prompt
    # argument is given, which hangs forever under subprocess otherwise.
    cp = subprocess.run(argv, stdin=subprocess.DEVNULL, check=False)
    return cp.returncode


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_setup(args):
    require_api_key()
    cfg = load_config()

    info("fetching your Render services...")
    services = list_services()
    if not services:
        die("no services found for this API key.")

    print()
    for idx, svc in enumerate(services):
        name = svc.get("name", "?")
        sid = svc.get("id", "?")
        stype = svc.get("type", "?")
        print(f"  [{idx}] {bold(name)}  {dim(sid)}  ({stype})")
    print()

    choice = input("Pick the backend service number: ").strip()
    if not choice.isdigit() or int(choice) >= len(services):
        die("invalid selection.")
    svc = services[int(choice)]
    cfg["serviceId"] = svc.get("id")
    cfg["ownerId"] = svc.get("ownerId") or (svc.get("owner") or {}).get("id")
    if not cfg["ownerId"]:
        # 兜底：从 /owners 拿第一个
        owners = render_get("/owners", {"limit": 1})
        if owners:
            first = owners[0].get("owner") if isinstance(owners[0], dict) else None
            cfg["ownerId"] = (first or {}).get("id")
    cfg.setdefault("agent", detect_agent() or "codex")
    save_config(cfg)

    # 环境体检
    print()
    info("environment check:")
    agent = detect_agent(cfg.get("agent"))
    print(f"  agent CLI : {green(agent) if agent else red('none found (install codex or cursor-agent)')}")
    gh = run(["gh", "auth", "status"], check=False, capture=True)
    print(f"  gh auth   : {green('ok') if gh.returncode == 0 else red('not authenticated (run: gh auth login)')}")
    print(f"  service   : {green(cfg['serviceId'])}")
    print(green("\nsetup complete. Try: uv run tools/selfheal/selfheal.py logs --since 6h"))


def _print_issues(issues: list[dict]):
    if not issues:
        print(green("no errors found in the selected window."))
        return
    print()
    for idx, g in enumerate(issues):
        head = f"[{idx}] x{g['count']}  {dim(g['last_seen'])}"
        print(bold(head))
        print("    " + red(g["signature"]))
    print()


def cmd_logs(args):
    cfg = load_config()
    levels = [s.strip() for s in args.level.split(",") if s.strip()]
    types = [s.strip() for s in args.type.split(",") if s.strip()]
    logs = fetch_logs(cfg, args.since, levels, types)
    info(f"fetched {len(logs)} log lines in the last {args.since}")
    issues = group_errors(logs)
    _print_issues(issues)


def _fix_issue(issue: dict, agent: str, base: str, auto: bool) -> str | None:
    slug = slugify(issue["signature"])
    branch = f"selfheal/{datetime.now().strftime('%Y%m%d')}-{slug}"

    info(f"branch {branch}")
    git("switch", "-c", branch, capture=False)
    try:
        rc = run_agent(agent, build_prompt(issue))
        if rc != 0:
            print(yellow(f"agent exited with code {rc}"))

        changed = git("status", "--porcelain")
        if not changed:
            print(yellow("agent made no changes - skipping this issue."))
            git("switch", base, capture=False)
            git("branch", "-D", branch, capture=False)
            return None

        print(bold("\n--- proposed diff ---"))
        run(["git", "--no-pager", "diff"], check=False, capture=False)
        print(bold("--- end diff ---\n"))

        if not auto:
            ok = input("Open a PR for this fix? [y/N] ").strip().lower()
            if ok != "y":
                print(yellow("discarded. reverting branch."))
                git("checkout", "--", ".", capture=False)
                git("switch", base, capture=False)
                git("branch", "-D", branch, capture=False)
                return None

        git("add", "-A", capture=False)
        title = f"fix: {issue['signature'][:70]}"
        body = (
            "Automated fix proposed by selfheal.\n\n"
            f"Occurrences: {issue['count']} (last seen {issue['last_seen']})\n\n"
            "```\n" + issue["excerpt"][:1500] + "\n```\n"
        )
        git("commit", "-m", title, "-m", body, capture=False)
        git("push", "-u", "origin", branch, capture=False)
        cp = run(["gh", "pr", "create", "--title", title, "--body", body,
                  "--base", base, "--head", branch], check=False, capture=True)
        url = (cp.stdout or "").strip()
        if cp.returncode == 0:
            print(green(f"PR opened: {url}"))
        else:
            print(red("gh pr create failed:\n" + (cp.stderr or "")))
            url = None
        return url
    finally:
        # 回到基础分支，便于处理下一个问题
        cur = git("rev-parse", "--abbrev-ref", "HEAD", check=False)
        if cur != base:
            git("switch", base, capture=False, check=False)


def cmd_run(args):
    cfg = load_config()
    agent = detect_agent(args.agent or cfg.get("agent"))
    if not agent:
        die("no agent CLI found. Install codex (or cursor-agent), or pass --agent.")

    ensure_clean_tree()
    base = default_branch()
    info(f"agent={agent}  base={base}")

    levels = [s.strip() for s in args.level.split(",") if s.strip()]
    types = [s.strip() for s in args.type.split(",") if s.strip()]
    logs = fetch_logs(cfg, args.since, levels, types)
    info(f"fetched {len(logs)} log lines in the last {args.since}")
    issues = group_errors(logs)
    if args.limit:
        issues = issues[: args.limit]
    _print_issues(issues)
    if not issues:
        return

    sel = input("Fix which? (e.g. 0,2 or 'all', empty to cancel): ").strip().lower()
    if not sel:
        print(dim("cancelled."))
        return
    if sel == "all":
        chosen = list(range(len(issues)))
    else:
        chosen = []
        for part in sel.split(","):
            part = part.strip()
            if part.isdigit() and int(part) < len(issues):
                chosen.append(int(part))
    if not chosen:
        die("no valid selection.")

    opened = []
    for idx in chosen:
        print(bold(f"\n=== fixing issue [{idx}] ==="))
        url = _fix_issue(issues[idx], agent, base, args.auto)
        if url:
            opened.append(url)

    print()
    if opened:
        print(green(f"opened {len(opened)} PR(s):"))
        for u in opened:
            print("  " + u)
    else:
        print(yellow("no PRs opened."))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        prog="selfheal",
        description="Read Render error logs, propose agent fixes, open PRs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser("setup", help="connect Render service + check environment")
    p_setup.set_defaults(func=cmd_setup)

    common = dict()
    p_logs = sub.add_parser("logs", help="fetch and group error logs (read-only)")
    p_logs.add_argument("--since", default="6h", help="time window, e.g. 30m, 6h, 2d")
    p_logs.add_argument("--level", default="error", help="comma list: error,warning")
    p_logs.add_argument("--type", default="app,build", help="comma list: app,build,request")
    p_logs.set_defaults(func=cmd_logs)

    p_run = sub.add_parser("run", help="interactive: pick issues, fix, open PRs")
    p_run.add_argument("--since", default="6h", help="time window, e.g. 30m, 6h, 2d")
    p_run.add_argument("--level", default="error", help="comma list: error,warning")
    p_run.add_argument("--type", default="app,build", help="comma list: app,build,request")
    p_run.add_argument("--agent", choices=list(AGENTS.keys()), help="override fix agent")
    p_run.add_argument("--limit", type=int, default=0, help="max issues to consider")
    p_run.add_argument("--auto", action="store_true", help="skip diff confirmation")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    load_env_file()
    # When stdout isn't a TTY (piped/redirected to a file), Python fully-buffers it,
    # which reorders our print() output relative to the unbuffered subprocess output
    # (git/gh/agent) sharing the same fd. Force line-buffering so logs interleave
    # in the order things actually happened.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    try:
        args.func(args)
    except KeyboardInterrupt:
        print()
        die("interrupted.", code=130)


if __name__ == "__main__":
    main()
