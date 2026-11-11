#!/usr/bin/env node
// 応答の言語が、ユーザーの直近の発言の言語から意図せずずれていたら、Haiku で見つけて言い直させる。
// 発言の言語を決めるのはユーザーの発言であり、応答だけを見て言語を判定しない。
import { spawnSync } from "node:child_process";
import fs from "node:fs";

const ROLE = `You check whether an AI assistant's reply is in the wrong language.
You receive the user's latest message in <user_message> and the assistant's reply in <reply>.

Step 1. Decide the target language. First look for an explicit request about the reply's language anywhere in the user's message (for example "answer in English", "英語で書いて", "in Japanese please"). If there is one, the target is the requested language, even when the rest of the message is written in another language. Otherwise the target is the language the message is written in.
Example: the message "この関数を説明して。英語で書いて" asks for English, so the target is English and an English reply is not drifted.
Step 2. Decide the language of the reply's prose. Ignore code, commands, identifiers, file paths, quotations, proper nouns and technical terms; technical terms in another language inside prose are normal.
Step 3. drifted is true only if the reply's prose language differs from the target language. If the reply has little or no prose (code or commands only, or very short), drifted is false.

Output only JSON: {"language": "<English name of the target language>", "reply_language": "<English name of the reply's prose language, or none>", "drifted": boolean}`;

const fail = (message) => {
  process.stderr.write(`${message}\n`);
  process.exit(1);
};

let input;
try {
  input = JSON.parse(fs.readFileSync(0, "utf8"));
} catch (e) {
  fail(`入力 JSON を読めない: ${e.message}`);
}
if (input.stop_hook_active || !input.last_assistant_message) process.exit(0);

// 発言の本文を返す。ユーザーが書いた地の文が無い行は空文字を返す。
const NOT_PROSE = /^(<task-notification>|<ci-monitor-event>|<local-command-stdout>|\[Request interrupted|<bash-input>)/;
const bodyOf = (row) => {
  const { content } = row.message ?? {};
  if (row.type !== "user" || row.isMeta || row.isCompactSummary) return "";
  const text = Array.isArray(content)
    ? content.filter((b) => b.type === "text").map((b) => b.text).join("\n")
    : content;
  if (typeof text !== "string") return "";
  const body = text.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, "").trim();
  if (body.includes("<command-name>")) return body.match(/<command-args>([\s\S]*?)<\/command-args>/)?.[1].trim() ?? "";
  return NOT_PROSE.test(body) ? "" : body;
};

// 正しい言語を決める発言は、prompt_id に一致する最後の行までで、本文が空でない最後の発言。
let userMessage;
try {
  const rows = fs.readFileSync(input.transcript_path, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
  const current = rows.findLastIndex((r) => r.promptId === input.prompt_id);
  if (current < 0) fail(`prompt_id ${input.prompt_id} に一致する行が会話記録に無い`);
  userMessage = rows.slice(0, current + 1).map(bodyOf).findLast(Boolean);
} catch (e) {
  fail(`会話記録を読めない: ${e.message}`);
}
if (!userMessage) process.exit(0);

const asked = spawnSync(
  "claude",
  ["--print", "--safe-mode", "--no-session-persistence", "--model", "haiku", "--system-prompt", ROLE],
  {
    input: `<user_message>\n${userMessage}\n</user_message>\n<reply>\n${input.last_assistant_message}\n</reply>`,
    encoding: "utf8",
    timeout: 50_000,
    env: { ...process.env, CLAUDE_CODE_DISABLE_ADVISOR_TOOL: "1" },
  },
);
if (asked.status !== 0) fail(`Haiku の呼び出しに失敗した: ${asked.error?.message ?? asked.stderr}`);

let verdict;
try {
  verdict = JSON.parse(asked.stdout.trim().replace(/^```(?:json)?\s*|\s*```$/g, ""));
} catch {
  fail(`Haiku の答えを JSON として読めない: ${asked.stdout}`);
}
if (typeof verdict?.drifted !== "boolean" || typeof verdict.language !== "string" || !verdict.language) {
  fail(`Haiku の答えが決めた形に合わない: ${asked.stdout}`);
}

if (verdict.drifted) {
  process.stdout.write(
    JSON.stringify({
      decision: "block",
      reason: `Your previous reply drifted from the user's language. Restate your previous reply in ${verdict.language}. Do not redo the work.`,
    }),
  );
}
