#!/usr/bin/env node
// 視座が具体に下りたとき、その材料を Fable に読ませ、目的や管理の視点へ引き上げる一文の問いを Claude へ渡す。
//   PostCompact : 会話の要約を読ませる。
//   PostToolUse : メインエージェントの直近の会話記録と、直前の Agent 呼び出しを読ませる。
import { spawnSync } from "node:child_process";
import fs from "node:fs";

const EXCERPT_ENTRIES = 30;
const EXCERPT_ITEM_CHARS = 1500;

const ROLES = {
  PostCompact: `You are an executive coach.
Based on the "summary", formulate simple, abstract, question-based advice that leads directly to the underlying objective. Output only the advice in one sentence.`,
  PostToolUse: `You are an executive coach for a manager agent who delegates all work to subagents.
Based on the "transcript" (the manager's recent conversation) and the "delegation" (the subagent call that just returned), formulate simple, abstract, question-based advice that pulls the manager's view back from concrete details to management concerns: the objective, priorities, delegation, and the next decision. Output only the advice in one sentence.`,
};

const clip = (text) =>
  text.length > EXCERPT_ITEM_CHARS ? `${text.slice(0, EXCERPT_ITEM_CHARS)}…` : text;

// メインエージェントの記録だけを、発言・ツール呼び出し・ツール結果の順に平らな文字列へ直す。
function renderEntry({ type, message }) {
  const blocks = typeof message.content === "string" ? [{ type: "text", text: message.content }] : message.content;
  const parts = blocks.flatMap((b) => {
    if (b.type === "text") return [`${type}: ${b.text}`];
    if (b.type === "tool_use") return [`${type} → ${b.name}: ${JSON.stringify(b.input)}`];
    if (b.type === "tool_result") {
      const body = typeof b.content === "string" ? b.content : JSON.stringify(b.content);
      return [`result: ${body}`];
    }
    return [];
  });
  return parts.map(clip).join("\n");
}

function transcriptExcerpt(path) {
  const entries = fs
    .readFileSync(path, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .filter((e) => (e.type === "user" || e.type === "assistant") && !e.isSidechain);
  return entries.slice(-EXCERPT_ENTRIES).map(renderEntry).filter(Boolean).join("\n\n");
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const event = input.hook_event_name;
const role = ROLES[event];
if (!role) fail(`未知の hook_event_name: ${event}`);

// サブエージェントの中で発火した呼び出しには助言しない。
if (event === "PostToolUse" && input.agent_id) process.exit(0);

// 要約・記録は対象者自身の言葉で書かれている。囲んで示すことで、
// 続きを書く側ではなく、外から問う側として読ませる。
const material =
  event === "PostCompact"
    ? `<summary>\n${input.compact_summary}\n</summary>`
    : `<transcript>\n${transcriptExcerpt(input.transcript_path)}\n</transcript>\n\n<delegation>\n${clip(JSON.stringify(input.tool_input))}\n${clip(JSON.stringify(input.tool_response))}\n</delegation>`;

const asked = spawnSync(
  "claude",
  ["--print", "--safe-mode", "--no-session-persistence", "--model", "fable", "--system-prompt", role],
  {
    input: material,
    encoding: "utf8",
    // 助言役を無効にする。有効なままだと「作業を進めよ」と促され、外から問う役割が崩れる。
    env: { ...process.env, CLAUDE_CODE_DISABLE_ADVISOR_TOOL: "1" },
  },
);

if (asked.status !== 0) fail(`Fable の呼び出しに失敗した: ${asked.error?.message ?? asked.stderr}`);

const advice = asked.stdout.trim();
process.stdout.write(
  JSON.stringify(
    event === "PostCompact"
      ? { additionalContext: advice }
      : { hookSpecificOutput: { hookEventName: event, additionalContext: advice } },
  ),
);
