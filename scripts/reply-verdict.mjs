// Stop フックが、直近のユーザーの発言と最後の応答を Haiku に渡し、応答への判定を JSON で受け取るための処理。
import { spawnSync } from "node:child_process";
import fs from "node:fs";

const fail = (message) => {
  process.stderr.write(`${message}\n`);
  process.exit(1);
};

// 発言の本文を返す。ユーザーが書いた地の文が無い行は空文字を返す。
// 「Orca restarted」「[Orca: 」で始まる行と、本文が「Continue where you left off.」だけの行は、Orca が会話へ自動で差し込む定型文。
const NOT_PROSE = /^(<task-notification>|<ci-monitor-event>|<local-command-stdout>|\[Request interrupted|<bash-input>|Orca restarted[.,] |\[Orca: )|^Continue where you left off\.$/;
const bodyOf = (row) => {
  if (row.type !== "user" || row.isMeta || row.isCompactSummary) return "";
  const { content } = row.message ?? {};
  const text = Array.isArray(content)
    ? content.filter((b) => b.type === "text").map((b) => b.text).join("\n")
    : content;
  if (typeof text !== "string") return "";
  const body = text.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, "").trim();
  if (body.includes("<command-name>")) return body.match(/<command-args>([\s\S]*?)<\/command-args>/)?.[1].trim() ?? "";
  return NOT_PROSE.test(body) ? "" : body;
};

// 標準入力から Stop フックの入力を読み、Haiku の判定を返す。
// role は Haiku への指示、maxMessages は渡す発言の件数、isValid は判定が決めた形に合うかを確かめる関数。
// 言い直しの途中のとき、応答が無いとき、ユーザーの発言が無いときは、判定せずに終了する。
export function replyVerdict(role, maxMessages, isValid) {
  let input;
  try {
    input = JSON.parse(fs.readFileSync(0, "utf8"));
  } catch (e) {
    fail(`入力 JSON を読めない: ${e.message}`);
  }
  if (input.stop_hook_active || !input.last_assistant_message) process.exit(0);

  // Haiku に渡す発言は、prompt_id に一致する最後の行までで、本文が空でない最後の maxMessages 件。
  let rows;
  try {
    rows = fs.readFileSync(input.transcript_path, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
  } catch (e) {
    fail(`会話記録を読めない: ${e.message}`);
  }
  const current = rows.findLastIndex((r) => r.promptId === input.prompt_id);
  if (current < 0) fail(`prompt_id ${input.prompt_id} に一致する行が会話記録に無い`);
  const userMessages = rows.slice(0, current + 1).map(bodyOf).filter(Boolean).slice(-maxMessages);
  if (userMessages.length === 0) process.exit(0);

  const asked = spawnSync(
    "claude",
    ["--print", "--safe-mode", "--no-session-persistence", "--model", "haiku", "--system-prompt", role],
    {
      input: `${userMessages.map((m) => `<user_message>\n${m}\n</user_message>`).join("\n")}\n<reply>\n${input.last_assistant_message}\n</reply>`,
      encoding: "utf8",
      timeout: 50_000,
      env: { ...process.env, CLAUDE_CODE_DISABLE_ADVISOR_TOOL: "1" },
    },
  );
  // claude は失敗の理由を標準出力へ書くことがあるため、標準エラーとあわせて伝える。
  if (asked.status !== 0) {
    fail(`Haiku の呼び出しに失敗した（終了 ${asked.status ?? asked.signal}）: ${asked.error?.message ?? `${asked.stderr}${asked.stdout}`}`);
  }

  let verdict;
  try {
    verdict = JSON.parse(asked.stdout.trim().replace(/^```(?:json)?\s*|\s*```$/g, ""));
  } catch {
    fail(`Haiku の答えを JSON として読めない: ${asked.stdout}`);
  }
  if (!isValid(verdict)) fail(`Haiku の答えが決めた形に合わない: ${asked.stdout}`);
  return verdict;
}

// 応答を止め、reason のとおりに言い直させる。
export const block = (reason) => process.stdout.write(JSON.stringify({ decision: "block", reason }));
