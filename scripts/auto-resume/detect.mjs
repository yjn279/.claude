#!/usr/bin/env node
// 会話が使用量の上限で止まったかを判定し、解除の時刻に一度だけ起きる予約を登録する。
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
const AGENT_DIR = path.join(os.homedir(), "Library", "LaunchAgents");
const LABEL_PREFIX = "com.claude.auto-resume";

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

function writeState(state) {
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  fs.writeFileSync(STATE_FILE, `${JSON.stringify(state, null, 2)}\n`);
}

function which(command) {
  const found = spawnSync("/usr/bin/which", [command], { encoding: "utf8" });
  const line = found.stdout.trim().split("\n")[0];
  if (!line) throw new Error(`${command} が見つからない`);
  return line;
}

function plistXml({ label, args, workdir, logPath, at }) {
  const argXml = args.map((a) => `    <string>${a.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</string>`).join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${label}</string>
  <key>ProgramArguments</key>
  <array>
${argXml}
  </array>
  <key>WorkingDirectory</key><string>${workdir}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Month</key><integer>${at.getMonth() + 1}</integer>
    <key>Day</key><integer>${at.getDate()}</integer>
    <key>Hour</key><integer>${at.getHours()}</integer>
    <key>Minute</key><integer>${at.getMinutes()}</integer>
  </dict>
  <key>StandardOutPath</key><string>${logPath}</string>
  <key>StandardErrorPath</key><string>${logPath}</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
`;
}

function schedule({ sessionId, cwd, at }) {
  const label = `${LABEL_PREFIX}.${sessionId}`;
  const plistPath = path.join(AGENT_DIR, `${label}.plist`);
  const loaded = spawnSync("/bin/launchctl", ["print", `gui/${process.getuid()}/${label}`], { stdio: "ignore" });
  if (fs.existsSync(plistPath) || loaded.status === 0) return { label, plistPath, skipped: true };

  const stamp = `${at.getFullYear()}${`${at.getMonth() + 1}`.padStart(2, "0")}${`${at.getDate()}`.padStart(2, "0")}`
    + `-${`${at.getHours()}`.padStart(2, "0")}${`${at.getMinutes()}`.padStart(2, "0")}`;
  const logPath = path.join(LOG_DIR, `${stamp}_${sessionId}.log`);
  fs.mkdirSync(LOG_DIR, { recursive: true });
  fs.mkdirSync(AGENT_DIR, { recursive: true });

  const args = [
    "/usr/bin/caffeinate", "-i",
    "/bin/bash", path.join(HERE, "resume.sh"),
    sessionId, cwd, which("claude"), CONFIG.resumePrompt, label, String(Math.floor(at.getTime() / 1000)),
    String(CONFIG.lateLimitMinutes * 60),
  ];
  fs.writeFileSync(plistPath, plistXml({ label, args, workdir: cwd, logPath, at }));

  const boot = spawnSync("/bin/launchctl", ["bootstrap", `gui/${process.getuid()}`, plistPath], { encoding: "utf8" });
  if (boot.status !== 0) {
    fs.rmSync(plistPath, { force: true });
    throw new Error(`予約の登録に失敗した: ${boot.stderr.trim()}`);
  }
  return { label, plistPath, logPath, skipped: false };
}

function decide(payload) {
  const { session_id: sessionId, cwd, last_assistant_message: text } = payload;
  if (!sessionId || !cwd || !text) return `入力が足りない: ${JSON.stringify(payload)}`;
  if (!LIMIT_RE.test(text)) return `${sessionId}: 上限の文面ではない`;

  const now = new Date();
  const epoch = resetEpoch(text, now);
  if (epoch === null) return `${sessionId}: 解除の時刻が読めない（${text}）`;

  const state = readState();
  const count = state[sessionId]?.count ?? 0;
  if (count >= CONFIG.maxResumesPerSession) return `${sessionId}: 再開 ${count} 回に達した。諦める`;

  const at = new Date(epoch + CONFIG.resetBufferMinutes * 60_000);
  at.setSeconds(0, 0);

  const result = schedule({ sessionId, cwd, at });
  if (result.skipped) return `${sessionId}: 同じ予約が既にある。何もしない`;

  state[sessionId] = { count: count + 1, scheduledFor: at.toISOString(), cwd };
  writeState(state);
  return `${sessionId}: ${at.toISOString()} に再開を予約した（通算 ${count + 1} 回目）`;
}

// 有効・無効の切り替え。設定ファイルか環境変数のどちらでも止められる。
if (CONFIG.enabled !== true || /^(0|off|false)$/i.test(process.env.CLAUDE_AUTO_RESUME ?? "")) {
  process.exit(0);
}

const workerPayload = process.argv[2] === "--worker" ? process.argv[3] : null;
if (workerPayload) {
  // 切り離された子。判定と予約はここで行う。
  const payload = JSON.parse(fs.readFileSync(workerPayload, "utf8"));
  fs.rmSync(workerPayload, { force: true });
  try {
    log(decide(payload));
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
