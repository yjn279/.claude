---
name: eli-15
description: Turns information into a diagram-only HTML explainer that a 15-year-old high school student can follow. Technical terms stay exactly as written and are never defined, since the reader knows them; the words around them become simpler. Decides what the reader will do after reading, cuts what that task does not need, and rebuilds the rest as a chain of numbered sections that leads to that action, with an overview map at the top showing each section's conclusion and how one leads to the next. Every section is a labeled inline SVG or HTML figure that says one thing, built around the units the reader works with instead of the source's order, with no captions, lead paragraphs, or source notes outside the figures. Works in light and dark themes and at phone width. Use when the user asks for a diagram, a visual explanation, an explainer of a deck or document, or an HTML page that newcomers or students can follow. Not for slides or Markdown documents.
---

# ELI-15

情報を、 15 歳の高校生が読んで分かる HTML の図解にする。専門用語は知っている 15 歳の高校生が、各図だけを見てその図が言う 1 つのことを自分の言葉で言え、上の全体図だけを見て章がどうつながり何に行き着くかを言えれば合格とする。構成、図の形、色、書体は題材に合わせてその都度いちばん伝わる形を選ぶ。

## Content

内容は資料の要約ではなく、読み手が読んだあとにする行動へ向かう筋道として組み立てる。

- 書き始める前に、読み手がこのページを読んだあとに何をするかを 1 つ決め、それに要らないことを外す。残りはその行動に行き着く章の鎖に組み直し、各章を、前の章の結論を受けて次の章へ渡す 1 つの問いにする。前後の章とのつながりを 1 文で言えない章は、外すか問いを立て直す。
- 要素は、読み手が実際に扱う単位で分けてつなぐ。資料の項目を同じ形で並べただけでは、項目ごとのカードでも表でも何も言わないので、配信先の区分や担当する工程のように読み手が手を動かす単位を軸に取り直し、要素どうしを矢印でつなぐ。
- 専門用語は言い換えず、語の意味も説明しないが、そのものの役割や働きは書く。専門用語とは固有名詞、ツールの画面に出るラベル、チームが呼び名として使う言葉のことで、テーブル名やオプション名のような実装の中だけの名前は含まない。やさしくするのは、用語のまわりの言葉と文の組み立てである。
- 資料にあることだけを書く。決まっていないことは、まとめの章を作らず、図の中のその要素に「案」や「未定」と添える。

## Page

ページはタイトル、全体図、番号付きの章だけで組み、図の外に文を置かない。図の下の注釈、冒頭の出典や説明、締めの文は、図が言うべきことを図の外へ逃がし、読み手の目も止めないので、伝えたいことは図の中のラベルとして書き、 Humanizer Skill で自然に整える。ページのデザインは `artifact-design` のスキルを読んでから作る。

- 全体図：タイトルのすぐ下に、章を縦に並べた図を置く。各章の箱には問いとその章の結論を 1 行で書き、箱と箱の間の矢印には前の章が次の章へどうつながるかを書く。箱を押すとその章へ移れるようにする。
- 章：見出しに全体図と同じ番号を付け、見出しの下には図だけを置く。後半の章ほど資料の文や表をそのまま並べたくなるので、最後の章まで図にする。
- 見た目：色は変数で決め、ライトとダークの両方で読めるようにする。スマホの幅でもページが横にはみ出さないようにし、横に長い図は図の枠だけを横にスクロールさせる。
- 形式： Artifact として公開しないときは、 doctype から書いた完全な HTML にする。 `artifact-design` の決まりのうち、 doctype や head を書かないことや `data-theme` での切り替えのように公開のしくみに関わるものは、 Artifact のときだけ当てはめる。

## Figures

図は `artifact-diagramming` のスキルを読んでから作り、読み手が図だけで仕組みを追えるようにする。

- 図は仕組みを描き、何がどこを通り、どこでつながるかを見せる。矢印には何が起きるかを書き、 1 つの図で言うことは 1 つにする。図の中の番号は、本当に順番があるときだけ付ける。
- ER 図やシーケンス図のように決まった記法のある図を求められたら、その図の種類が持つ要素はすべて残し、記法を知らないと読めない記号は使わない。記号が担っていた意味は、記号があった場所に言葉で書く。たとえばカラスの足の代わりに線のそばへ「 1 人が何件も持つ」と書き、戻りを表す破線の矢印の代わりに実線の矢印に「結果を返す」と書く。

## Review

図がすべてできたら、ファイルに書き出し、ブラウザで表示できるときは表示してから最初から読み通し、図の外に文が残っていないか、全体図の結論と矢印が各章の図と合っているか、項目を並べただけの図がないかを確かめる。次に、全部の図をまとめて 1 回 advisor に助言を求める。 advisor は会話の記録を読むので、呼ぶ前に冒頭の合格の基準を観点として文で書く。用語の説明や図の外の文を足す方向の指摘は受け取らず、もらった指摘で図を直す。
