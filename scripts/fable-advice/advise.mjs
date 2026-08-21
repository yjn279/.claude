#!/usr/bin/env node
// 作業の途中で、いままでのやり取りを Fable に読ませ、その助言を Claude の次の判断へ渡す。
// 道具を使い終えた直後（PostToolBatch フック）に標準入力から呼ばれ、
// 前回の助言から一定の時間が空いたときだけ Fable を呼ぶ。
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const INTERVAL_MINUTES = 30; // 助言と助言のあいだに空ける時間
const TRANSCRIPT_LINES = 80; // 会話の末尾から読み取る行数
const DIGEST_LIMIT = 8000; // Fable へ渡す文字数の上限
const NO_ADVICE = "NO_ADVICE"; // 言うべきことがないときに Fable が返す合図

const ROLE = `あなたは、作業中の会話を外から眺めて助言する立場にある。
いままでのやり取りを読み、進めている作業が目的からずれていないか、見落としや遠回りがないかを見る。
言うべきことがなければ ${NO_ADVICE} とだけ返す。
助言があるときは、日本語で3行以内、何が問題でどう直すかを具体的に書く。ほめ言葉と要約は書かない。`;

// 会話の1つの部品を、Fable が読める1行の文へ直す。ここに出てこない種類の部品は捨てる。
const READERS = {
  text: (part) => part.text,
  tool_use: (part) => `[${part.name}] ${JSON.stringify(part.input)}`,
};

/** 会話の記録の末尾を読み、Fable へ渡す文章を組み立てる。 */
function readConversation(transcriptPath) {
  const lines = fs.readFileSync(transcriptPath, "utf8").trimEnd().split("\n");
  const turns = [];

  for (const line of lines.slice(-TRANSCRIPT_LINES)) {
    const message = JSON.parse(line).message;
    if (!message?.content) continue;

    // 発言の中身は、文字列のときと部品の並びのときがある。並びの形へそろえる。
    const parts = Array.isArray(message.content)
      ? message.content
      : [{ type: "text", text: message.content }];

    const said = parts.map((part) => READERS[part.type]?.(part) ?? "").filter(Boolean).join("\n");
    if (said) turns.push(`${message.role}: ${said}`);
  }

  return turns.join("\n\n").slice(-DIGEST_LIMIT);
}

const event = JSON.parse(fs.readFileSync(0, "utf8"));
const claudeHome = process.env.CLAUDE_CONFIG_DIR ?? path.join(os.homedir(), ".claude");
const lastAdvised = path.join(claudeHome, "fable-advice", `${event.session_id}.last`);

if (Date.now() - (fs.statSync(lastAdvised, { throwIfNoEntry: false })?.mtimeMs ?? 0) < INTERVAL_MINUTES * 60_000) {
  process.exit(0);
}

// 呼び出しの前に時刻を記録し、Fable の返事を待つあいだに次の呼び出しが重ならないようにする。
fs.mkdirSync(path.dirname(lastAdvised), { recursive: true });
fs.writeFileSync(lastAdvised, "");

// Fable はこの設定を読み込まずに動かす。フックが自分自身を呼び出す入れ子を断つため。
const asked = spawnSync(
  "claude",
  ["--print", "--safe-mode", "--no-session-persistence", "--model", "claude-fable-5", "--system-prompt", ROLE],
  { input: readConversation(event.transcript_path), encoding: "utf8" },
);

if (asked.status !== 0) {
  process.stderr.write(`Fable の呼び出しに失敗した: ${asked.error?.message ?? asked.stderr}\n`);
  process.exit(1);
}

const advice = asked.stdout.trim();
if (advice.startsWith(NO_ADVICE)) process.exit(0);

process.stdout.write(JSON.stringify({ additionalContext: advice }));
