#!/usr/bin/env node
// 応答の言語が、ユーザーの発言が決める言語から意図せずずれていたら、Haiku で見つけて言い直させる。
// どの発言が言語を決めるかは Haiku が判定する。応答だけを見て言語を判定しない。
import { block, replyVerdict } from "../reply-verdict.mjs";

const ROLE = `You check whether an AI assistant's reply is in the wrong language.
You receive the user's recent messages, oldest first, each inside <user_message>, and the assistant's reply in <reply>.

Step 1. Decide the target language from the user's messages.
- The newest message that has prose of its own decides the language. Messages without prose of their own do not decide it: short acknowledgements ("ok", "LGTM", "yes"), pasted logs or stack traces, URLs, file paths, and command arguments with no prose.
- An explicit request about the reply's language (for example "answer in English", "以降は英語で答えて", "in Japanese please") sets the target to the requested language. It stays in force until a newer message is written in another language or makes a different request. A request inside a message wins over the language that message is written in.
Example: the message "この関数を説明して。英語で書いて" asks for English, so the target is English and an English reply is not drifted.
- If no message decides the language, set "language" to "none" and drifted to false.
Step 2. Decide the language of the reply's prose. Ignore code, commands, identifiers, file paths, quotations, proper nouns and technical terms; technical terms in another language inside prose are normal.
Step 3. drifted is true only if the reply's prose language differs from the target language. If the reply has no prose (code or commands only), drifted is false. A short status remark, such as one about progress or about what is being waited for, is prose and is judged like any other.

Output only JSON: {"language": "<English name of the target language, or none>", "reply_language": "<English name of the reply's prose language, or none>", "drifted": boolean}`;

const verdict = replyVerdict(ROLE, 10, (v) => typeof v?.drifted === "boolean" && typeof v.language === "string" && v.language !== "");

if (verdict.drifted && verdict.language.toLowerCase() !== "none") {
  block(`Your previous reply drifted from the user's language. Restate your previous reply in ${verdict.language}. Do not redo the work. Write all later replies in ${verdict.language} as well, including short remarks made while working or waiting.`);
}
