#!/usr/bin/env node
// 報告に前提・結論・根拠のいずれかが欠けていたら、Haiku で見つけて言い直させる。
// 質問への回答、事実を確かめる問い返し、単純な操作の報告は対象にしない。
import { block, replyVerdict } from "../reply-verdict.mjs";

// 報告に求める要点。CLAUDE.md の Reporting に対応する。
const POINTS = {
  premise:
    "the premise (what the user asked for, or which project or task this is; what the assistant did or changed is the conclusion, never the premise)",
  conclusion: "the conclusion (the outcome, and whatever the user is asked to approve, decide or discuss)",
  rationale: "the rationale (the reasons or evidence behind the conclusion and the decisions made)",
};

const ROLE = `You check whether an AI coding assistant's last message of a turn reports its work the way its user requires.
You receive the user's recent messages, oldest first, each inside <user_message>, and the assistant's message in <reply>.

Step 1. Classify the reply as one of:
- "none": not a report. The reply itself is what the user asked for (an answer, an explanation, a description, a draft), or it is casual conversation, or it is a note that work is still under way, or it only asks the user for a fact about the request or the environment, such as which file or which environment is meant. A question about how the work should be done is never "none".
- "brief": a report of a simple operation, where one short statement of what was done tells the user everything. Examples: merging a pull request, committing, pushing, renaming a file, running one command the user asked for.
- "full": any other report. The reply tells the user the outcome of a task the assistant carried out, such as changing code or investigating a problem, or it asks the user how the work should be done: to approve a proposed course of action, or to choose among or discuss options for the approach or the design.
If you cannot tell, choose "none".

Step 2. Only for "full", quote for each point the words of the reply that convey it, in at most ten words on one line, or give "" when the reply has no such words:
${Object.entries(POINTS).map(([name, meaning]) => `- "${name}": ${meaning}`).join("\n")}
Never quote a user message. The user's messages are there only to help you classify the reply, so a point the reply leaves to them gets "".
Form does not matter: headings, labels, a fixed order and Markdown are not required, and one sentence can be enough for a point.

Output only JSON: {"kind": "none" | "brief" | "full", ${Object.keys(POINTS).map((name) => `"${name}": "<quote or empty>"`).join(", ")}}`;

const verdict = replyVerdict(
  ROLE,
  3,
  (v) => ["none", "brief", "full"].includes(v?.kind) && Object.keys(POINTS).every((name) => typeof v[name] === "string"),
);

const missing = Object.keys(POINTS).filter((name) => !verdict[name].trim());
if (verdict.kind === "full" && missing.length > 0) {
  block(`Your previous reply is a report that leaves out ${missing.map((name) => POINTS[name]).join("; ")}. Restate the report so that it conveys every point it left out. Do not redo the work.`);
}
