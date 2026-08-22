#!/usr/bin/env node
// 会話が要約されたあと、その要約を Fable に読ませ、返ってきた助言を Claude へ渡す。
// 長く一人で作業するうちに下がった視座を、目的まで引き上げるために置く。
import { spawnSync } from "node:child_process";
import fs from "node:fs";

const ROLE = `You are an executive coach.
Based on the "summary", formulate simple, abstract, question-based advice that leads directly to the underlying objective. Output only the advice in one sentence.`;

// 要約は対象者自身の言葉で書かれている。要約であることを囲んで示すことで、
// 続きを書く側ではなく、外から問う側として読ませる。
const summary = JSON.parse(fs.readFileSync(0, "utf8")).compact_summary;
const asked = spawnSync(
  "claude",
  ["--print", "--safe-mode", "--no-session-persistence", "--model", "fable", "--system-prompt", ROLE],
  {
    input: `<summary>\n${summary}\n</summary>`,
    encoding: "utf8",
    // 助言役を無効にする。有効なままだと「作業を進めよ」と促され、外から問う役割が崩れる。
    env: { ...process.env, CLAUDE_CODE_DISABLE_ADVISOR_TOOL: "1" },
  },
);

if (asked.status !== 0) {
  process.stderr.write(`Fable の呼び出しに失敗した: ${asked.error?.message ?? asked.stderr}\n`);
  process.exit(1);
}

process.stdout.write(JSON.stringify({ additionalContext: asked.stdout.trim() }));
