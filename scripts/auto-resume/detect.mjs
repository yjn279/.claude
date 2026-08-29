#!/usr/bin/env node
// 会話が使用量の上限で止まったかを判定し、解除の時刻まで待って、その会話を再開する。
// StopFailure フックから標準入力で呼ばれる。
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const HERE = import.meta.dirname;
const CONFIG = JSON.parse(fs.readFileSync(path.join(HERE, "config.json"), "utf8"));
const CLAUDE_HOME = process.env.CLAUDE_CONFIG_DIR ?? path.join(os.homedir(), ".claude");
const STATE_FILE = path.join(CLAUDE_HOME, "auto-resume", "state.json");
const LOG_DIR = path.join(CLAUDE_HOME, "resume-logs");

// 「You've hit your session limit · resets 9:10pm (Asia/Tokyo)」の形を読む。
const LIMIT_RE = /hit your [^.\n]*limit/i;
const RESET_RE = /resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)/i;
const ZONE_RE = /\(([A-Za-z_]+\/[A-Za-z_+-]+|UTC)\)/;

function log(line) {
  fs.mkdirSync(LOG_DIR, { recursive: true });
  fs.appendFileSync(path.join(LOG_DIR, "detect.log"), `${new Date().toISOString()} ${line}\n`);
}

function readStdin() {
  try {
    return fs.readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

/** 指定の地域における、その時刻の世界標準時からのずれ（ミリ秒）。 */
function zoneOffsetMs(zone, date) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: zone, hour12: false,
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).formatToParts(date).map((p) => [p.type, p.value]),
  );
  const asUtc = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour % 24, +parts.minute, +parts.second);
  return asUtc - date.getTime();
}

/** 指定の地域の壁掛け時計の日時を、絶対時刻に直す。 */
function zonedEpoch(zone, y, m, d, hour, minute) {
  const naive = Date.UTC(y, m - 1, d, hour, minute, 0);
  let epoch = naive;
  for (let i = 0; i < 2; i++) epoch = naive - zoneOffsetMs(zone, new Date(epoch));
  return epoch;
}

function zonedYmd(zone, date) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" })
      .formatToParts(date).map((p) => [p.type, p.value]),
  );
  return { y: +parts.year, m: +parts.month, d: +parts.day };
}

/** 上限の文面から解除の絶対時刻を求める。読み取れないときは null を返す。 */
function resetEpoch(text, now) {
  const matched = RESET_RE.exec(text);
  if (!matched) return null;

  let hour = +matched[1] % 12;
  if (matched[3].toLowerCase() === "pm") hour += 12;
  const minute = matched[2] ? +matched[2] : 0;

  const zoneName = ZONE_RE.exec(text)?.[1];
  let zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (zoneName) {
    try {
      zoneOffsetMs(zoneName, now);
      zone = zoneName;
    } catch {
      // 未知の地域名のときは、この端末の地域として読む
    }
  }

  const today = zonedYmd(zone, now);
  let epoch = zonedEpoch(zone, today.y, today.m, today.d, hour, minute);
  if (epoch <= now.getTime()) epoch = zonedEpoch(zone, today.y, today.m, today.d + 1, hour, minute);
  return epoch;
}

function readState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
  } catch {
    return {};
  }
}

function updateState(sessionId, entry) {
  const state = readState();
  state[sessionId] = { ...state[sessionId], ...entry };
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  fs.writeFileSync(STATE_FILE, `${JSON.stringify(state, null, 2)}\n`);
}

function alive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function which(command) {
  const found = spawnSync("/usr/bin/which", [command], { encoding: "utf8" });
  const line = found.stdout.trim().split("\n")[0];
  if (!line) throw new Error(`${command} が見つからない`);
  return line;
}

/** 待つべきかを決める。待たないときは、その理由の文字列を返す。 */
function decide(payload) {
  const { session_id: sessionId, cwd, transcript_path: transcript, last_assistant_message: text } = payload;
  if (!sessionId || !cwd || !transcript || !text) return `入力が足りない: ${JSON.stringify(payload)}`;
  if (!LIMIT_RE.test(text)) return `${sessionId}: 上限の文面ではない`;

  const now = new Date();
  const epoch = resetEpoch(text, now);
  if (epoch === null) return `${sessionId}: 解除の時刻が読めない（${text}）`;

  const waiting = readState()[sessionId];
  if (waiting?.pid && alive(waiting.pid)) return `${sessionId}: 同じ会話を既に待っている。何もしない`;

  const count = waiting?.count ?? 0;
  if (count >= CONFIG.maxResumesPerSession) return `${sessionId}: 再開 ${count} 回に達した。諦める`;

  const at = new Date(epoch + CONFIG.resetBufferMinutes * 60_000);
  at.setSeconds(0, 0);

  updateState(sessionId, { count: count + 1, scheduledFor: at.toISOString(), cwd, transcript, pid: process.pid });
  return { sessionId, cwd, transcript, at, count: count + 1 };
}

/** 解除の時刻まで待ち、会話を再開する。 */
async function waitAndResume({ sessionId, cwd, transcript, at }) {
  // 眠りから覚めた分もそのまま数えるため、実時刻を繰り返し見比べて待つ。
  while (Date.now() < at.getTime()) await sleep(Math.min(30_000, at.getTime() - Date.now()));

  const lateMinutes = Math.round((Date.now() - at.getTime()) / 60_000);
  if (lateMinutes > CONFIG.lateLimitMinutes) {
    updateState(sessionId, { pid: null, result: `${lateMinutes} 分の遅れで見送り` });
    return `${sessionId}: 予定より ${lateMinutes} 分遅れたため再開しない`;
  }
  if (!fs.existsSync(transcript)) {
    updateState(sessionId, { pid: null, result: "会話の記録がない" });
    return `${sessionId}: 会話の記録が見つからない（${transcript}）`;
  }

  const now = new Date();
  const stamp = `${now.getFullYear()}${`${now.getMonth() + 1}`.padStart(2, "0")}${`${now.getDate()}`.padStart(2, "0")}`
    + `-${`${now.getHours()}`.padStart(2, "0")}${`${now.getMinutes()}`.padStart(2, "0")}`;
  const logPath = path.join(LOG_DIR, `${stamp}_${sessionId}.log`);
  fs.mkdirSync(LOG_DIR, { recursive: true });
  const out = fs.openSync(logPath, "a");

  // 再開のあいだは端末を眠らせない。
  const child = spawn("/usr/bin/caffeinate", ["-i", which("claude"), "--resume", sessionId, "--print", CONFIG.resumePrompt], {
    cwd, stdio: ["ignore", out, out],
  });
  const status = await new Promise((done) => child.on("exit", (code) => done(code ?? -1)));
  fs.closeSync(out);

  updateState(sessionId, { pid: null, result: `再開の終了コード ${status}` });
  return `${sessionId}: 再開して終了コード ${status}（出力は ${logPath}）`;
}

// 有効・無効の切り替え。設定ファイルか環境変数のどちらでも止められる。
if (CONFIG.enabled !== true || /^(0|off|false)$/i.test(process.env.CLAUDE_AUTO_RESUME ?? "")) {
  process.exit(0);
}

const workerPayload = process.argv[2] === "--worker" ? process.argv[3] : null;
if (workerPayload) {
  // 切り離した子。判定と、解除の時刻までの待機と、再開をここで行う。
  const payload = JSON.parse(fs.readFileSync(workerPayload, "utf8"));
  fs.rmSync(workerPayload, { force: true });
  try {
    const decided = decide(payload);
    if (typeof decided === "string") {
      log(decided);
    } else {
      log(`${decided.sessionId}: ${decided.at.toISOString()} まで待って再開する（通算 ${decided.count} 回目）`);
      log(await waitAndResume(decided));
    }
  } catch (error) {
    log(`失敗: ${error.stack ?? error}`);
    process.exit(1);
  }
} else {
  // フックから呼ばれた側。受け取ってすぐ返す。
  const raw = readStdin();
  if (!raw.trim()) process.exit(0);
  const payloadFile = path.join(os.tmpdir(), `claude-auto-resume-${process.pid}-${Date.now()}.json`);
  fs.writeFileSync(payloadFile, raw);
  spawn(process.execPath, [import.meta.filename, "--worker", payloadFile], {
    detached: true,
    stdio: "ignore",
  }).unref();
}
