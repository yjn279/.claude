#!/usr/bin/env node
// 会話が要約されたあと、その要約を Fable に読ませ、返ってきた問いかけを Claude へ渡す。
// 長く一人で作業するうちに狭まった視野を、目的まで引き戻すために置く。
import { spawnSync } from "node:child_process";
import fs from "node:fs";

const ROLE = `あなたは、長いあいだ一人で作業している別の作業者に、外から問いかける立場にある。
渡されるのは、その作業者がここまで何をしてきたかの要約である。

手順に埋もれて見えなくなっているものを探し、次を確かめる。

- 本来の目的から、いつのまにか離れていないか
- 解こうとしている問題の立て方そのものが、間違っていないか
- 作らずに済ませられるものを、作り込んでいないか
- 同じところを回り続けていないか

日本語で5行以内。問いかけを中心に、具体的に書く。
これまでの作業の要約と、ほめ言葉は書かない。`;

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
