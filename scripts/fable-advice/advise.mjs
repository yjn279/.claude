#!/usr/bin/env node
// 会話が要約されたあと、その要約を Fable に読ませ、返ってきた問いかけを Claude へ渡す。
// 長く一人で作業するうちに下がった視座を、目的まで引き上げるために置く。
import { spawnSync } from "node:child_process";
import fs from "node:fs";

const ROLE = `あなたはエグゼクティブコーチです。
与えられた内容について、本当の目的に最短で辿り着けるよう、抽象的でシンプルな問いかけを考えてください。問いのみを端的に出力すること。`;

// Fable にはこの設定を読ませない。周りの指示に染まらない、外からの目として答えさせるため。
const asked = spawnSync(
  "claude",
  ["--print", "--safe-mode", "--no-session-persistence", "--model", "claude-fable-5", "--system-prompt", ROLE],
  { input: JSON.parse(fs.readFileSync(0, "utf8")).compact_summary, encoding: "utf8" },
);

if (asked.status !== 0) {
  process.stderr.write(`Fable の呼び出しに失敗した: ${asked.error?.message ?? asked.stderr}\n`);
  process.exit(1);
}

process.stdout.write(JSON.stringify({ additionalContext: asked.stdout.trim() }));
