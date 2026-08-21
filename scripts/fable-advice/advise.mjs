#!/usr/bin/env node
// 会話が要約されたあと、その要約を Fable に読ませ、返ってきた問いかけを Claude へ渡す。
// 長く一人で作業するうちに下がった視座を、目的まで引き上げるために置く。
import { spawnSync } from "node:child_process";
import fs from "node:fs";

const ROLE = `あなたはエグゼクティブコーチです。
対象者の視座を高め、本質かつ価値最大である目的に最短で辿り着けるよう、1-3問程度のシンプルな問いかけを実践してください。`;

// 要約は対象者自身の言葉で書かれている。誰の何であるかを囲んで示し、
// 求めるものを末尾に置くことで、続きを書く側ではなく問う側として読ませる。
const summary = JSON.parse(fs.readFileSync(0, "utf8")).compact_summary;
const asked = spawnSync(
  "claude",
  ["--print", "--safe-mode", "--no-session-persistence", "--model", "claude-fable-5", "--system-prompt", ROLE],
  {
    input: `<対象者のこれまでの作業の要約>\n${summary}\n</対象者のこれまでの作業の要約>\n\n問いかけだけを返してください。`,
    encoding: "utf8",
  },
);

if (asked.status !== 0) {
  process.stderr.write(`Fable の呼び出しに失敗した: ${asked.error?.message ?? asked.stderr}\n`);
  process.exit(1);
}

process.stdout.write(JSON.stringify({ additionalContext: asked.stdout.trim() }));
