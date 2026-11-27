#!/usr/bin/env python3
"""Digest recent Claude Code session transcripts into one compact Markdown report.

Reads ~/.claude/projects/**/*.jsonl and the user-level config, and prints what
the offload skill weighs: what people ask for, what automation sends, which
models, advisors and subagents spend tokens on what, which tools and commands
repeat, and what is already configured. With --session it prints one session
as a condensed transcript instead. It only reads and writes nothing.
"""

import argparse
import collections
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

CLAUDE = Path.home() / ".claude"
PROJECTS = CLAUDE / "projects"
HOME = str(Path.home())

# Text that Claude Code, a hook or another session puts into a user turn. None of it is a request.
INTERRUPTED = "interrupted by the user"
INJECTED = (
    ("Stop hook feedback:", lambda rest: "Stop hook: " + clip(rest, 70)),
    ("Another Claude session sent a message:", "message from another session"),
    ("<task-notification>", "background task notification"),
    ("<system-reminder>", "system reminder"),
    ("Base directory for this skill:", lambda rest: "skill loaded: " + rest.split("\n", 1)[0].strip().rstrip("/").rsplit("/", 1)[-1]),
    ("This session is being continued", "summary after compaction"),
    ("[Request interrupted", INTERRUPTED),
    ("<local-command-", "local command output"),
    ("Caveat:", "local command output"),
    ("[Cross-session idle notice]", "idle notice from another session"),
)
INJECTED_ORIGINS = {"task-notification", "peer", "plugin"}
INJECTED_TURNS = {"task_notification", "system"}
COMMAND_RE = re.compile(r"<command-name>/?([^<]+)</command-name>")
ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
SCHEDULED_RE = re.compile(r'<scheduled-task name="([^"]+)"')
# Commands whose second word says what they do.
SUBCOMMAND_TOOLS = {
    "git", "gh", "npm", "npx", "pnpm", "yarn", "bun", "uv", "cargo", "docker", "brew", "orca",
    "ego-browser", "claude", "eas", "expo", "make", "go", "kubectl", "launchctl", "node",
}


def short_path(p):
    return p.replace(HOME, "~", 1) if p else "?"


def project(p):
    """Fold worktrees, Orca workspaces and temporary directories into the project they belong to."""
    if not p:
        return "?"
    if p.startswith(("/private/tmp/", "/tmp/", "/var/folders/")):
        return "(temporary directories)"
    p = re.sub(r"/(\.worktrees|\.claude/worktrees|\.trinity)/.*$", "", p)
    p = re.sub(r"^(.*/orca/workspaces/[^/]+)/[^/]+.*$", r"\1/*", p)
    return short_path(p)


def clip(text, n):
    text = re.sub(r"\s+", " ", text).strip().replace("|", "\\|")
    return text if len(text) <= n else text[: n - 1] + "…"


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def injected_label(text):
    for prefix, label in INJECTED:
        if text.startswith(prefix):
            return label(text[len(prefix):]) if callable(label) else label
    return None


def classify_user_record(rec):
    """Return (kind, text, command) for a user record. kind is human, relayed, scheduled, injected or None (a tool result)."""
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None, "", None
    text = text_of(content)
    command = None
    m = COMMAND_RE.search(text)
    if m:
        command = m.group(1).strip()
        args = ARGS_RE.search(text)
        text = args.group(1).strip() if args else ""
        if not text:
            return None, "", command
    m = SCHEDULED_RE.search(text)
    if m or rec.get("turnOrigin") == "scheduled":
        return "scheduled", m.group(1) if m else text, command
    label = injected_label(text)
    origin = rec.get("origin") if isinstance(rec.get("origin"), dict) else {}
    if label or rec.get("isMeta") or origin.get("kind") in INJECTED_ORIGINS or rec.get("turnOrigin") in INJECTED_TURNS:
        return "injected", label or clip(text, 60), command
    if origin.get("kind") == "human" or rec.get("promptSource") == "typed":
        return "human", text, command
    return "relayed", text, command


def tool_label(name, inp):
    if name != "Bash":
        return name
    cmd = (inp or {}).get("command", "")
    cmd = re.sub(r'"?\$\{[A-Z_]+:-([^}]+)\}"?', r"\1", cmd)
    cmd = re.sub(r"^\s*cd\s+\S+\s*(&&|;|\n)\s*", "", cmd)
    words = [w for w in cmd.split() if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)]
    if not words:
        return "Bash"
    head = re.split(r"[;&|]", words[0].strip("\"'"))[0].rsplit("/", 1)[-1] or words[0]
    if head in SUBCOMMAND_TOOLS and len(words) > 1 and not words[1].startswith("-"):
        head += " " + words[1]
    return "Bash:" + head


def usage_parts(msg):
    """Split one assistant message's usage into (model, is_advisor, counts) parts.

    A turn that consulted the advisor lists each model call under usage.iterations,
    and the top-level numbers leave the advisor call out, so read the iterations.
    """
    u = msg.get("usage") or {}
    model = msg.get("model") or "?"
    for it in u.get("iterations") or [u]:
        cc = it.get("cache_creation") or {}
        counts = {
            "input": it.get("input_tokens") or 0,
            "cache_write_5m": cc.get("ephemeral_5m_input_tokens") or 0,
            "cache_write_1h": cc.get("ephemeral_1h_input_tokens") or 0,
            "cache_read": it.get("cache_read_input_tokens") or 0,
            "output": it.get("output_tokens") or 0,
            "messages": 1,
        }
        if counts["cache_write_5m"] + counts["cache_write_1h"] != (it.get("cache_creation_input_tokens") or 0):
            sys.exit(f"cache write tokens of message {msg.get('id')} are not split into 5m and 1h; update digest.py")
        advisor = it.get("type") == "advisor_message"
        yield (it.get("model") or "?") if advisor else model, advisor, counts


def subagent_meta(p):
    path = p.with_suffix(".meta.json")
    return json.loads(path.read_text()) if path.exists() else {}


def records(path):
    """Yield user and assistant records. Stop on any line that cannot be parsed."""
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if '"type":"user"' not in line and '"type":"assistant"' not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                sys.exit(f"{path}:{n}: cannot parse transcript line: {e}")
            if rec.get("type") in ("user", "assistant"):
                yield rec


def stamp(rec):
    ts = rec.get("timestamp")
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else None


class Session:
    def __init__(self, sid):
        self.sid = sid
        self.cwd = None
        self.start = None
        self.first = None  # (kind, text) of the first request, even if it came before the window
        self.prompts = []  # (kind, text) of requests inside the window
        self.commands = collections.Counter()
        self.main_labels = []  # tool labels of the main agent's calls, in order; feeds the tool sequences table
        self.tool_counts = collections.Counter()  # tool label -> calls by the main agent and its subagents
        self.usage = collections.defaultdict(collections.Counter)  # (model, role) -> counts
        self.interrupts = 0
        self.has_records_in_window = False

    @property
    def kind(self):
        kinds = {k for k, _ in self.prompts} | ({self.first[0]} if self.first else set())
        for k in ("human", "scheduled", "relayed"):
            if k in kinds:
                return k
        return "other"

    @property
    def first_text(self):
        return self.first[1] if self.first else ""

    @property
    def group_key(self):
        return clip(self.first_text, 80)

    def output(self):
        return sum(u["output"] for u in self.usage.values())

    def main_models(self):
        c = collections.Counter({m: u["messages"] for (m, r), u in self.usage.items() if r == "main"})
        return [m for m, _ in c.most_common(2)]


class Digest:
    def __init__(self, cutoff):
        self.cutoff = cutoff
        self.sessions = {}
        self.tools = collections.defaultdict(lambda: {"calls": 0, "errors": 0, "sessions": set(), "roles": collections.Counter()})
        self.bash = collections.defaultdict(set)
        self.skills = collections.Counter()
        self.injected = collections.Counter()
        self.agents = collections.defaultdict(lambda: {"runs": 0, "out": 0, "tasks": []})
        self.counted_message_ids = set()  # assistant messages whose usage is already counted
        self.label_by_tool_id = {}  # id of every tool call -> its tool label, to attribute errors in results

    def session(self, sid):
        return self.sessions.setdefault(sid, Session(sid))

    def read(self, path, s, role):
        """Fold one transcript into session s. Return how many assistant turns in the window used each model."""
        turns_by_model = collections.Counter()
        for rec in records(path):
            inside = (stamp(rec) or self.cutoff) >= self.cutoff
            s.cwd = s.cwd or rec.get("cwd")
            s.start = s.start or rec.get("timestamp")
            if rec["type"] == "user":
                if inside:
                    self.tool_errors(rec)
                if role == "sub":
                    continue
                kind, text, command = classify_user_record(rec)
                if kind in ("human", "relayed", "scheduled") and s.first is None:
                    s.first = (kind, text)
                if not inside:
                    continue
                s.has_records_in_window = True
                if command:
                    s.commands[command] += 1
                if kind == "injected":
                    self.injected[text] += 1
                    s.interrupts += text == INTERRUPTED
                elif kind:
                    s.prompts.append((kind, text))
                continue
            msg = rec.get("message") or {}
            if not inside or msg.get("model") == "<synthetic>":
                continue
            s.has_records_in_window = True
            turns_by_model[msg.get("model") or "?"] += 1
            if msg.get("usage") and msg.get("id") not in self.counted_message_ids:
                self.counted_message_ids.add(msg.get("id"))
                for model, advisor, counts in usage_parts(msg):
                    s.usage[(model, f"advisor of {role}" if advisor else role)].update(counts)
            for b in msg.get("content") if isinstance(msg.get("content"), list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    self.tool_use(b, s, role)
        return turns_by_model

    def tool_errors(self, rec):
        content = (rec.get("message") or {}).get("content")
        for b in content if isinstance(content, list) else []:
            if isinstance(b, dict) and b.get("is_error") and b.get("tool_use_id") in self.label_by_tool_id:
                self.tools[self.label_by_tool_id[b["tool_use_id"]]]["errors"] += 1

    def tool_use(self, b, s, role):
        label = tool_label(b.get("name", "?"), b.get("input"))
        self.label_by_tool_id[b.get("id")] = label
        t = self.tools[label]
        t["calls"] += 1
        t["sessions"].add(s.sid)
        t["roles"][role] += 1
        s.tool_counts[label] += 1
        if role == "main":
            s.main_labels.append(label)
        if b.get("name") == "Bash":
            self.bash[clip(b["input"].get("command", ""), 120)].add(s.sid)
        if b.get("name") == "Skill":
            self.skills[b["input"].get("skill", "?")] += 1

    def load(self, files):
        for p in files:
            if "subagents" not in p.parts:
                self.read(p, self.session(p.stem), "main")
        for p in files:
            if "subagents" not in p.parts:
                continue
            s = self.session(p.parent.parent.name)
            before = s.output()
            turns_by_model = self.read(p, s, "sub")
            if not turns_by_model:
                continue
            meta = subagent_meta(p)
            a =self.agents[(meta.get("agentType", "?"), turns_by_model.most_common(1)[0][0])]
            a["runs"] += 1
            a["out"] += s.output() - before
            if len(a["tasks"]) < 4 and meta.get("description"):
                a["tasks"].append(meta["description"])
        self.sessions = {k: s for k, s in self.sessions.items() if s.has_records_in_window}


def variant_keys(texts):
    """For prompts of one group, return the lines that set each apart from the rest of the group.

    Lines are compared with digits masked, and a line counts as shared when at least half of the
    group contains it. What remains is usually the actual task inside a common template.
    """
    norm = lambda line: re.sub(r"\d+", "#", re.sub(r"\s+", " ", line).strip())
    lines = [[norm(l) for l in t.split("\n") if l.strip()] for t in texts]
    seen = collections.Counter(l for ls in lines for l in set(ls))
    keys = []
    for ls in lines:
        own = [l for l in ls if seen[l] * 2 < len(texts)]
        keys.append(clip(" / ".join(own[:2]), 100) if own else "(the shared text only)")
    return keys


def report(d, days, top):
    sessions = list(d.sessions.values())
    first_count = collections.Counter(s.group_key for s in sessions if s.first)
    routine = lambda s: s.kind == "scheduled" or (s.kind == "relayed" and first_count[s.group_key] >= 2)
    out = []
    w = out.append

    w(f"# Session digest: last {days} days, to {datetime.now():%Y-%m-%d %H:%M}\n")
    w("Session kinds. human: a person typed at least one prompt. scheduled: a scheduled task started it. "
      "relayed: prompts came through the SDK (Orca, `claude -p`, bots), so a person and automation cannot be told apart by the record; "
      "a relayed session whose first prompt no other session shares is most likely a person. other: only injected text. "
      "Tokens count only what happened inside the window; a session's first prompt may be older.\n")
    kinds = collections.Counter(s.kind for s in sessions)
    runs = sum(a["runs"] for a in d.agents.values())
    w(f"{len(sessions)} sessions and {runs} subagent runs. " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()) + ".\n")

    w("## Projects\n\n| project | human | scheduled | relayed | other | interrupts | output tokens |\n| :-- | --: | --: | --: | --: | --: | --: |")
    proj = collections.defaultdict(collections.Counter)
    for s in sessions:
        c = proj[project(s.cwd)]
        c[s.kind] += 1
        c["interrupts"] += s.interrupts
        c["out"] += s.output()
    for cwd, c in sorted(proj.items(), key=lambda x: -x[1]["out"])[:top]:
        w(f"| {cwd} | {c['human']} | {c['scheduled']} | {c['relayed']} | {c['other']} | {c['interrupts']} | {c['out']:,} |")

    w("\n## Tokens by model\n\nrole main: the session's own agent. sub: its subagents. advisor of main / sub: advisor calls those agents made, "
      "billed to the advisor model. Price these with current rates from the `claude-api` skill.\n")
    w("| model | role | session kind | calls | input | cache write 5m | cache write 1h | cache read | output |\n"
      "| :-- | :-- | :-- | --: | --: | --: | --: | --: | --: |")
    agg = collections.defaultdict(collections.Counter)
    for s in sessions:
        for (model, role), u in s.usage.items():
            agg[(model, role, s.kind)].update(u)
    for (model, role, kind), u in sorted(agg.items(), key=lambda x: -(x[1]["output"] + x[1]["input"] / 10)):
        w(f"| {model} | {role} | {kind} | {u['messages']:,} | {u['input']:,} | {u['cache_write_5m']:,} | {u['cache_write_1h']:,} "
          f"| {u['cache_read']:,} | {u['output']:,} |")

    w("\n## Subagents\n\n| agent type | model | runs | output tokens | sample tasks |\n| :-- | :-- | --: | --: | :-- |")
    for (atype, model), a in sorted(d.agents.items(), key=lambda x: -x[1]["out"])[:top]:
        w(f"| {atype} | {model} | {a['runs']} | {a['out']:,} | {' / '.join(clip(t, 50) for t in a['tasks'])} |")

    w("\n## One-off requests\n\nSessions whose first prompt no other session shares, newest first. These are what people ask for. "
      "Pass the id to `--session` to read one.\n")
    w("| start | id | kind | project | prompts | commands | output tokens | first request |\n| :-- | :-- | :-- | :-- | --: | :-- | --: | :-- |")
    oneoff = sorted((s for s in sessions if s.first and not routine(s)), key=lambda s: s.start or "", reverse=True)
    for s in oneoff[: top * 2]:
        command_list = ", ".join(f"/{c}" for c in s.commands)
        w(f"| {(s.start or '')[:16]} | {s.sid[:8]} | {s.kind} | {project(s.cwd)} | {len(s.prompts)} | {command_list} | {s.output():,} "
          f"| {clip(s.first_text, 150)} |")

    w("\n## Routine session groups\n\nScheduled sessions, and relayed sessions whose first prompt two or more sessions share, grouped by "
      "that prompt. Variants show the part of the prompt that differs inside a group, which is usually the actual task.\n")
    w("| sessions | main models | output tokens | per session | top tools | first prompt |\n| --: | :-- | --: | --: | :-- | :-- |")
    groups = collections.defaultdict(list)
    for s in sessions:
        if routine(s):
            groups[s.group_key].append(s)
    ranked = sorted(groups.values(), key=lambda g: -sum(s.output() for s in g))[:top]
    for g in ranked:
        out_sum = sum(s.output() for s in g)
        models = collections.Counter(m for s in g for m in s.main_models())
        tools = sum((s.tool_counts for s in g), collections.Counter())
        w(f"| {len(g)} | {', '.join(m for m, _ in models.most_common(2))} | {out_sum:,} | {out_sum // len(g):,} "
          f"| {', '.join(t for t, _ in tools.most_common(3))} | {clip(g[0].first_text, 110)} |")
    for g in ranked:
        texts = [s.first_text for s in g]
        if len(set(texts)) < 2:
            continue
        variants = collections.defaultdict(lambda: [0, 0])
        for s, key in zip(g, variant_keys(texts)):
            variants[key][0] += 1
            variants[key][1] += s.output()
        if len(variants) < 2:
            continue
        w(f"\nVariants of \"{clip(g[0].first_text, 50)}\":\n\n| sessions | output tokens | differing part |\n| --: | --: | :-- |")
        for text, (n, o) in sorted(variants.items(), key=lambda x: -x[1][1])[:top]:
            w(f"| {n} | {o:,} | {text} |")

    w("\n## Repeated follow-ups\n\nWhole prompts after the first, sent in two or more sessions: approvals, corrections and nudges that "
      "keep coming back. Phrases inside longer prompts are not matched; search for those.\n")
    w("| sessions | times | kind | prompt |\n| --: | --: | :-- | :-- |")
    follow = collections.defaultdict(lambda: {"sessions": set(), "times": 0, "kinds": collections.Counter()})
    for s in sessions:
        prompts = s.prompts[1:] if s.prompts and s.first and s.prompts[0][1] == s.first[1] else s.prompts
        for kind, text in prompts:
            f = follow[clip(text, 100)]
            f["sessions"].add(s.sid)
            f["times"] += 1
            f["kinds"][kind] += 1
    repeated_prompts = sorted(((k, f) for k, f in follow.items() if len(f["sessions"]) >= 2), key=lambda x: -len(x[1]["sessions"]))
    for text, f in repeated_prompts[:top]:
        w(f"| {len(f['sessions'])} | {f['times']} | {'/'.join(f['kinds'])} | {text} |")
    if not repeated_prompts:
        w("| 0 | 0 | | (none) |")

    w("\n## Slash commands and skills\n\n| name | slash command | Skill tool |\n| :-- | --: | --: |")
    command_counts = sum((s.commands for s in sessions), collections.Counter())
    for name in sorted(set(command_counts) | set(d.skills), key=lambda n: -(command_counts[n] + d.skills[n]))[:top]:
        w(f"| {name} | {command_counts[name]} | {d.skills[name]} |")

    w("\n## Tools\n\n| tool | calls | errors | sessions | by main | by sub |\n| :-- | --: | --: | --: | --: | --: |")
    for label, t in sorted(d.tools.items(), key=lambda x: -x[1]["calls"])[: top + 10]:
        w(f"| {label} | {t['calls']} | {t['errors']} | {len(t['sessions'])} | {t['roles']['main']} | {t['roles']['sub']} |")

    w("\n## Repeated shell commands\n\nIdentical commands run in three or more sessions.\n\n| sessions | command |\n| --: | :-- |")
    repeated_commands = sorted(((len(v), k) for k, v in d.bash.items() if len(v) >= 3), reverse=True)[:top]
    for n, cmd in repeated_commands:
        w(f"| {n} | `{cmd}` |")
    if not repeated_commands:
        w("| 0 | (none) |")

    w("\n## Repeated tool sequences\n\nThree-step sequences of the main agent, consecutive repeats collapsed, in three or more sessions.\n\n"
      "| sessions | sequence |\n| --: | :-- |")
    grams = collections.defaultdict(set)
    for s in sessions:
        seq = [x for i, x in enumerate(s.main_labels) if i == 0 or x != s.main_labels[i - 1]]
        for i in range(len(seq) - 2):
            g = tuple(seq[i : i + 3])
            if len(set(g)) >= 2:
                grams[g].add(s.sid)
    for g, sids in sorted(grams.items(), key=lambda x: -len(x[1]))[:top]:
        if len(sids) >= 3:
            w(f"| {len(sids)} | {' → '.join(g)} |")

    w("\n## Injected text\n\nWhat hooks, notifications and other sessions put into user turns. Hook feedback that keeps firing means "
      "the agent keeps missing that rule.\n\n| times | text |\n| --: | :-- |")
    for label, n in d.injected.most_common(top):
        w(f"| {n} | {label} |")

    w("\n## Existing configuration\n")
    out.extend(configuration(sessions))
    return "\n".join(out)


def configuration(sessions):
    lines = []
    w = lines.append
    names = lambda d, pat="*": sorted(p.stem for p in d.glob(pat) if not p.name.startswith(".")) if d.exists() else []
    w("- Skills: " + (", ".join(names(CLAUDE / "skills")) or "(none)"))
    w("- Agents: " + (", ".join(names(CLAUDE / "agents", "*.md")) or "(none)"))
    w("- Rules: " + (", ".join(names(CLAUDE / "rules", "**/*.md")) or "(none)"))
    w("- Desktop scheduled tasks: " + (", ".join(names(CLAUDE / "scheduled-tasks")) or "(none)"))
    settings_path = CLAUDE / "settings.json"
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    keys = {k: settings[k] for k in ("model", "advisorModel", "effortLevel", "outputStyle") if k in settings}
    keys.update({k: v for k, v in settings.get("env", {}).items() if re.search(r"MODEL|EFFORT|ADVISOR|THINKING", k)})
    w("- Model settings: " + (", ".join(f"{k}={v}" for k, v in keys.items()) or "(defaults)"))
    w("- Plugins: " + (", ".join(k for k, v in settings.get("enabledPlugins", {}).items() if v) or "(none)"))
    own, other = [], []
    for event, groups in settings.get("hooks", {}).items():
        hook_commands = [h.get("command") or h.get("prompt") or h.get("type", "") for g in groups for h in g.get("hooks", [])]
        mine = [re.sub(r".*\.claude/(scripts|skills)/([^/\"]+).*", r"\2", c) for c in hook_commands if re.search(r"\.claude/(scripts|skills)", c)]
        (own if mine else other).append(f"{event} ({', '.join(mine)})" if mine else event)
    w("- Hooks with own scripts: " + (", ".join(own) or "(none)"))
    w("- Hooks with others' commands only: " + (", ".join(other) or "(none)"))
    w(f"- User CLAUDE.md: {'yes' if (CLAUDE / 'CLAUDE.md').exists() else 'no'}")
    w("\nProject-level configuration:\n")
    for cwd in sorted({s.cwd for s in sessions if s.cwd and s.cwd != HOME}):
        base = Path(cwd)
        parts = ["CLAUDE.md"] if (base / "CLAUDE.md").exists() else []
        for sub in ("skills", "agents", "commands", "rules"):
            found = names(base / ".claude" / sub)
            if found:
                parts.append(f"{sub}: {', '.join(found)}")
        proj_settings = base / ".claude" / "settings.json"
        if proj_settings.exists() and json.loads(proj_settings.read_text()).get("hooks"):
            parts.append("hooks")
        if parts:
            w(f"- {short_path(cwd)}: " + "; ".join(parts))
    return lines


def dump(target, width):
    """Print one session as a condensed transcript, then list its subagent runs."""
    path = Path(target).expanduser()
    if not path.exists():
        found = sorted(PROJECTS.glob(f"*/{target}*.jsonl"))
        if len(found) != 1:
            sys.exit(f"{len(found)} sessions match {target!r}; pass a longer id or the transcript path")
        path = found[0]
    print(f"# {short_path(str(path))}\n")
    for rec in records(path):
        ts = (rec.get("timestamp") or "")[5:16].replace("T", " ")
        if rec["type"] == "user":
            kind, text, command = classify_user_record(rec)
            if command:
                print(f"{ts} /{command}")
            if kind:
                print(f"{ts} user [{kind}]: {clip(text, width)}")
            content = (rec.get("message") or {}).get("content")
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                    print(f"{ts}   ! error: {clip(text_of(b.get('content')) or str(b.get('content')), width // 2)}")
            continue
        msg = rec.get("message") or {}
        for b in msg.get("content") if isinstance(msg.get("content"), list) else []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and b.get("text", "").strip():
                print(f"{ts} assistant ({msg.get('model')}): {clip(b['text'], width)}")
            elif b.get("type") == "tool_use":
                inp = b.get("input") or {}
                arg = inp.get("command") or inp.get("description") or inp.get("file_path") or inp.get("skill") or json.dumps(inp, ensure_ascii=False)
                print(f"{ts}   {tool_label(b.get('name', '?'), inp)}: {clip(str(arg), width // 2)}")
    subs = sorted((path.parent / path.stem / "subagents").glob("*.jsonl"))
    if subs:
        print("\n## Subagent runs\n")
        for p in subs:
            meta = subagent_meta(p)
            print(f"- {short_path(str(p))}: {meta.get('agentType', '?')}, {meta.get('description', '')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7, help="how many recent days to read (default 7)")
    ap.add_argument("--top", type=int, default=25, help="rows per table (default 25)")
    ap.add_argument("--session", metavar="ID_OR_PATH", help="print one session (an id prefix or a transcript path) instead")
    ap.add_argument("--width", type=int, default=300, help="characters per line in --session (default 300)")
    args = ap.parse_args()

    if args.session:
        dump(args.session, args.width)
        return
    cutoff = time.time() - args.days * 86400
    files = [p for p in PROJECTS.glob("**/*.jsonl") if p.stat().st_mtime >= cutoff]
    if not files:
        sys.exit(f"no transcripts modified in the last {args.days} days under {PROJECTS}")
    d = Digest(cutoff)
    d.load(files)
    print(report(d, args.days, args.top))


if __name__ == "__main__":
    main()
