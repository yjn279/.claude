// グローバル登録された再利用ワークフロー（切り出し元: catenaria-dev/landing-page）。
// 前提: カレントの作業ディレクトリが landing-page 互換のリポジトリ構成であること
//   - lp-system/RUBRIC.md（ゴール基準）・lp-system/briefs/<slug>.{md,gate.json}（入力）
//   - scripts/lp-capture.sh・scripts/lp-checks.sh（機械ゲート・撮影）
//   - clients/<slug>/index.html（成果物の出力先）
// パスは全てリポジトリルートからの相対。詳細は landing-page の lp-system/PIPELINE.md を参照。
export const meta = {
  name: 'lp-improvement-loop',
  description: 'ブリーフからLPを生成し、機械ゲート+審査員パネル+敵対監査でRUBRIC合格まで自動改善するループ',
  whenToUse: '地元企業LPの新規制作・改善を lp-system/RUBRIC.md 基準で自動収束させるとき。args: {slug, runId, startedAt, maxIters?}',
  phases: [
    { title: 'Setup', detail: 'run dir・ベースライン記録' },
    { title: 'Loop', detail: 'Generate→Gate→Judge→Audit→Record を合格まで反復' },
  ],
}

// ---------- 入力 ----------
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const slug = A.slug
const runId = A.runId
const startedAt = A.startedAt || 'unknown'
const maxIters = A.maxIters || 5
if (!slug || !runId) throw new Error(`args: {slug, runId, startedAt} が必須 (received: ${JSON.stringify(args).slice(0, 200)})`)

const BRIEF = `lp-system/briefs/${slug}.md`
const GATE = `lp-system/briefs/${slug}.gate.json`
const RUBRIC = 'lp-system/RUBRIC.md'
const RUN = `lp-system/runs/${runId}`

// ---------- ルーブリック登録（RUBRIC.md v1.1.0 と一致させること） ----------
// 主観性・リスクの高いカテゴリ（copy/design/trust）は2審査員の最小値合議
const CATEGORIES = {
  strategy: {
    label: 'Strategy（戦略・新PASONA構成・オファー設計）', ids: ['A1', 'A2', 'A3'],
    personas: ['ダイレクトレスポンスマーケティングとLP構成設計（新PASONA）の専門家'],
  },
  copy: {
    label: 'Copywriting（コピー・メッセージング）', ids: ['B1', 'B2', 'B3', 'B4'],
    personas: ['一流のセールスコピーライター（流入文脈との接続と説得構造に厳しい）', '出版社出身の編集者・校閲者（日本語の自然さ・固有性・誤字に厳しい）'],
  },
  design: {
    label: 'Visual Design（ビジュアル・アートディレクション）', ids: ['C1', 'C2', 'C3'],
    personas: ['受賞歴のあるアートディレクター（生成AI既定値のデザインを一目で見抜く）', 'ブランドデザイナー兼タイポグラファ（トークン規律・組版・造形の一貫性に厳しい）'],
  },
  ux: {
    label: 'Conversion UX（電話CV導線・モバイルUX）', ids: ['D1', 'D2', 'D3', 'D4'],
    personas: ['CRO（コンバージョン率最適化）コンサルタント兼モバイルUX専門家（電話CVの障壁設計に精通）'],
  },
  trust: {
    label: 'Trust & Compliance（事実整合・法令）', ids: ['E1', 'E2', 'E3'],
    personas: ['景品表示法・業種別広告規制に通じたリーガルチェッカー', 'ファクトチェッカー（LP全文とブリーフFactsの突合専門。JSON-LD・meta・属性・リンク先まで読む）'],
  },
  tech: {
    label: 'Technical Floor（a11y・レスポンシブ・実装）', ids: ['F1', 'F2', 'F3'],
    personas: ['アクセシビリティとレスポンシブ実装に厳格なフロントエンドエンジニア'],
  },
}
const ALL_IDS = Object.values(CATEGORIES).flatMap((c) => c.ids)
const PASS_TOTAL = 85
const PASS_CATEGORY_PCT = 0.7
const PASS_CRITERION_MIN = 3

// ---------- スキーマ ----------
const GEN_SCHEMA = {
  type: 'object', required: ['summary', 'captureDone'],
  properties: {
    summary: { type: 'string' },
    sectionsTouched: { type: 'array', items: { type: 'string' } },
    captureDone: { type: 'boolean' },
  },
}
const GATE_SCHEMA = {
  type: 'object', required: ['pass', 'failureCount', 'failures', 'warnings'],
  properties: {
    pass: { type: 'boolean' },
    failureCount: { type: 'integer' },
    failures: { type: 'array', items: { type: 'object', required: ['id', 'detail'], properties: { id: { type: 'string' }, detail: { type: 'string' } } } },
    warnings: { type: 'array', items: { type: 'string' } },
  },
}
const JUDGE_SCHEMA = {
  type: 'object', required: ['category', 'scores', 'blockers', 'fixes'],
  properties: {
    category: { type: 'string' },
    scores: {
      type: 'array',
      items: {
        type: 'object', required: ['id', 'score', 'evidence', 'rationale'],
        properties: {
          id: { type: 'string' },
          score: { type: 'integer', minimum: 0, maximum: 5 },
          evidence: { type: 'array', minItems: 1, items: { type: 'object', required: ['ref', 'note'], properties: { ref: { type: 'string', description: 'path:line または スクリーンショット名+縦位置(例: slice-2.png 上から600px付近)' }, note: { type: 'string' } } } },
          rationale: { type: 'string' },
        },
      },
    },
    blockers: { type: 'array', items: { type: 'object', required: ['title', 'detail', 'evidence'], properties: { title: { type: 'string' }, detail: { type: 'string' }, evidence: { type: 'string' } } } },
    fixes: { type: 'array', items: { type: 'object', required: ['priority', 'instruction'], properties: { priority: { type: 'string', enum: ['blocker', 'high', 'medium', 'low'] }, criterion: { type: 'string' }, instruction: { type: 'string' }, expectedGain: { type: 'string' } } } },
  },
}
const AUDIT_SCHEMA = {
  type: 'object', required: ['adjustments', 'blockerVerdicts', 'remeasure', 'notes'],
  properties: {
    adjustments: { type: 'array', items: { type: 'object', required: ['id', 'from', 'to', 'reason', 'evidence'], properties: { id: { type: 'string' }, from: { type: 'integer' }, to: { type: 'integer' }, reason: { type: 'string' }, evidence: { type: 'string' } } } },
    blockerVerdicts: { type: 'array', items: { type: 'object', required: ['blockerId', 'valid', 'reason'], properties: { blockerId: { type: 'string' }, valid: { type: 'boolean' }, reason: { type: 'string' } } } },
    remeasure: { type: 'array', items: { type: 'object', required: ['id', 'reason'], properties: { id: { type: 'string' }, reason: { type: 'string', description: '低得点の根拠証拠が事実誤認である説明' } } } },
    notes: { type: 'string' },
  },
}
const SETUP_SCHEMA = {
  type: 'object', required: ['target', 'targetExists'],
  properties: { target: { type: 'string' }, targetExists: { type: 'boolean' } },
}

// ---------- ヘルパ ----------
const retry = async (fn, label) => {
  let r = await fn(false)
  if (r === null) { log(`${label}: 失敗→リトライ`); r = await fn(true) }
  return r
}

// ---------- Setup ----------
phase('Setup')
const setup = await retry(
  (isRetry) => agent(
    `LP改善ループの実行環境を準備する。作業ディレクトリはカレントのリポジトリルート（全パスはここからの相対）。
1. ${GATE} を読み、"target" フィールド（LPのHTMLパス）を取得する。
2. mkdir -p で ${RUN} と、targetの親ディレクトリを作成する。
3. \`git status --porcelain > ${RUN}/baseline-status.txt\` でベースラインを記録する。
4. targetファイルが存在するか確認する。
StructuredOutputで {target, targetExists} を返す。それ以外の作業はしない。`,
    { label: isRetry ? 'setup-retry' : 'setup', schema: SETUP_SCHEMA, model: 'haiku' }
  ),
  'setup'
)
if (!setup) throw new Error('setup agent failed twice')
const TARGET = setup.target

// ---------- 反復 ----------
phase('Loop')
const totals = []
const minCriterions = []
const gateRedCounts = []
const blockerCounts = []
const timeline = []
let fixlist = null
let strategyRevision = false
let strategyRevisionReason = ''
let passed = false
let finalAgg = null
let interrupted = false
let interruptedAt = null

for (let i = 1; i <= maxIters; i++) {
  const ITER = `${RUN}/iter-${i}`
  const SHOTS = `${ITER}/shots`
  const P = `Iter ${i}`

  // --- Generate ---
  const genPrompt = `あなたは地元企業LP制作の一流のクラフトマン（戦略・コピー・デザイン・実装の全てを一人で担う）。

## 任務
${TARGET} を${setup.targetExists || i > 1 ? '改善' : '新規制作'}し、${RUBRIC} の合格基準（総合85点・全ゲートgreen・全基準3以上）を満たす品質に到達させる。

## 必読（この順で読む。読まずに書き始めることを禁ずる）
1. ${RUBRIC} 全文 — 唯一の合否基準。特に「Hard Gates」「AI Default Checklist」（1項目でも該当するとC1は2点以下）
2. ${BRIEF} 全文 — 唯一の事実源。Facts表とGoal節に無い事実・数値・固有名詞は一切書かない（捏造は即FAIL）。Traffic（流入文脈）にFVを正対させ、Legal Notesの全項目を守る
3. ${GATE} — 機械ゲートの禁止パターン・必須文字列・数値許可リスト
${i > 1 ? '4. 前回の修正指示リスト（下記）— blocker/highは全件必須対応' : '4. ブリーフ「References」節の品質参考実装（視覚様式の流用は禁止。水準の参照のみ）'}

${fixlist ? `## 修正指示リスト\n${JSON.stringify(fixlist, null, 2)}` : ''}

${strategyRevision ? `## 戦略改訂モード（発動理由: ${strategyRevisionReason}）\n部分修正を禁止する。コピー方針またはアートディレクションの根本から再設計し、大胆に作り直すこと。` : ''}

## 実装規約（機械ゲートが実測検査する）
- 単一ファイルHTML・モバイルファースト・width:min(100%,430px)キャンバスのデスクトップ中央配置
- 可視CTAに data-cta 属性: FV(390x844)内に1つ以上＋position:fixed/stickyの追従CTA＋最終CTA。各タップ領域44x44px以上。主CTAは許可リストのtel:を直接指す
- 全CTAクリックは単一のdispatch関数を経由し、tel:番号はコード上1箇所に集約（計測差し替え容易性=F3）
- tel CTAの近傍（同一視認範囲）に営業時間・定休日を表示（D2）
- ページ内の全<a href>は許可リスト内のみ。#アンカーは参照先ID実在
- viewport / lang="ja" / title / meta description / LocalBusiness系JSON-LD（telephone・address・openingHours。aggregateRating/reviewは禁止）
- prefers-reduced-motion で全テキストが静的に可視・無限アニメゼロ（実測される）。sr-only実テキスト
- コントラスト: axe-core違反ゼロ。グラデ/画像上のテキストは機械判定不能になるため8件以下に抑える
- 数値は許可リスト（allowedNumbers/allowedClaims）内のみ。3桁以上の数字・単位付き数値は全て検査される
- 禁止語に注意: 必ず/絶対（警告対象。案内文でも避ける）、最上級表現、無料、価格、口コミ表現

## 作業手順
1. 上記を読み、${TARGET} を書く（既存があれば改善。戦略改訂モードなら作り直し）
2. \`bash scripts/lp-capture.sh ${TARGET} ${SHOTS}\` でスクリーンショットを撮る
3. ${SHOTS}/manifest.json を読み、view-390.png・view-430.png・desktop-1280-full.png と **全ての slice-*.png** を自分の目でReadし、視覚破綻・コントラスト不足・詰まり・AI既定値パターンを見つけたらHTMLを直して再撮影する（このセルフチェックを最低1回行う）
4. \`node scripts/lp-checks.mjs --html ${TARGET} --gate ${GATE} --out ${ITER} --shots ${SHOTS}\` を実行し、failuresが残っていれば直して再撮影→再実行（ゲートgreenまで自分で回す）
5. \`cp ${TARGET} ${ITER}/snapshot.html\` でスナップショットを残す

## 変更禁止（G0違反で即FAIL）
${RUBRIC}・lp-system/briefs/・lp-system/references/・lp-system/history.jsonl・scripts/・.claude/・index.html(関城接骨院)・他クライアントのLP

StructuredOutputで {summary, sectionsTouched, captureDone} を返す。`
  const gen = await retry((r) => agent(genPrompt, { label: r ? `gen-${i}-retry` : `gen-${i}`, phase: P }), `gen-${i}`)

  // --- Gate（独立再撮影を強制。Generatorの成果物・自己申告を信用しない） ---
  let gate = await retry(
    (r) => agent(
      `機械ゲート実行係。何も修正してはいけない（判定のみ）。手順:
1. \`bash scripts/lp-capture.sh ${TARGET} ${SHOTS}\` を**無条件に再実行**する（既存スクリーンショットの有無に関わらず上書き。独立した証拠を作るため）
2. \`bash scripts/lp-checks.sh ${TARGET} ${GATE} ${ITER} ${RUN}/baseline-status.txt ${SHOTS}\` を実行する
3. 出力された ${ITER}/gate.json を読み、pass / failureCount / failures / warnings を**一字一句改変せず**StructuredOutputで返す（failureCountはfailures配列の長さと一致していること）`,
      { label: r ? `gate-${i}-retry` : `gate-${i}`, phase: P, schema: GATE_SCHEMA }
    ),
    `gate-${i}`
  )
  // 整合性チェック: 転記の取りこぼし検出
  if (gate && gate.failureCount !== gate.failures.length) {
    log(`gate-${i}: failureCount不整合（申告${gate.failureCount}≠配列${gate.failures.length}）→再実行`)
    gate = await agent(
      `${ITER}/gate.json をReadし、pass / failureCount / failures / warnings をそのままStructuredOutputで返す。改変・要約禁止。`,
      { label: `gate-${i}-reread`, phase: P, schema: GATE_SCHEMA }
    )
  }
  const gateOk = !!gate && gate.pass === true && gate.failureCount === 0

  // --- Judge panel（カテゴリ×ペルソナで並列・相互独立。copy/design/trustは2審査員） ---
  const judgeJobs = []
  for (const [key, cat] of Object.entries(CATEGORIES)) {
    cat.personas.forEach((persona, pi) => {
      judgeJobs.push({ key, cat, persona, tag: `${key}${cat.personas.length > 1 ? `-${pi + 1}` : ''}` })
    })
  }
  const judgePrompt = (j) => `あなたは${j.persona}。独立した懐疑的審査員として「${j.cat.label}」カテゴリのみを採点する。

## 採点規律（違反した採点は無効）
- まず ${RUBRIC} を読み、担当カテゴリ（基準 ${j.cat.ids.join(', ')}）のアンカー（5/3/1）と4点・2点の規則を正確に把握する${j.key === 'design' ? '。「AI Default Checklist」を全項目照合し、1項目でも該当すればC1は2点以下' : ''}${j.key === 'strategy' || j.key === 'copy' ? '。A2/B1は「視覚審査の必須手順」（view-390.pngのFVのみ→3秒テスト→その後全量）に従う' : ''}
- 「点を与える理由」ではなく「点を与えない理由」を先に探す。迷ったら低い方。ただし証拠は正確に（事実誤認の低得点は監査で差し戻される）
- 全ての採点に証拠を最低1つ: コードは path:line、視覚はスクリーンショット名+縦位置（例: slice-2.png 上から600px付近。slice-Nは N×1500px 起点）。監査員が再特定できる粒度で
- 他カテゴリの判断・過去イテレーション（${RUN}/iter-* の過去分）は見ない
- ${BRIEF} のFacts表・Goal節に無い事実主張を1つでも見つけたら blockers に挙げる（外部知識で正しくても違反）${j.key === 'trust' ? '。JSON-LD・meta・alt/aria属性・リンク先・details内テキストまで全文走査すること' : ''}

## 審査対象
- コード: ${TARGET}
- ブリーフ（唯一の事実源。Traffic・Legal Notes含む）: ${BRIEF}
- スクリーンショット: ${SHOTS}/ — まず manifest.json を読み、view-390/view-360/view-430/desktop-1280-full と **全ての slice-*.png（sliceCount全数）** をReadで目視する
- 機械ゲート結果（参考。warningsの「審査員への引き継ぎ」事項はあなたの担当なら必ず確認）: ${ITER}/gate.json

## 出力
StructuredOutputで返す: category="${j.key}", scores=[${j.cat.ids.map((id) => `{id:"${id}",...}`).join(', ')}]（**この${j.cat.ids.length}基準を過不足なく**・0〜5整数）, blockers（捏造・法令違反など即FAIL事項）, fixes（priority: blocker|high|medium|low、具体的で実行可能な修正指示。criterionに対象基準ID）`

  const judgeResults = await parallel(
    judgeJobs.map((j) => () =>
      agent(judgePrompt(j), { label: `judge-${j.tag}-${i}`, phase: P, schema: JUDGE_SCHEMA })
        .then((res) => ({ job: j, res }))
    )
  )
  // ID検証＋リトライ
  const validJudges = []
  const unjudgedCategories = new Set(Object.keys(CATEGORIES))
  const judgedOnce = new Set()
  for (const jr of judgeResults.filter(Boolean)) {
    const want = new Set(jr.job.cat.ids)
    const got = new Set((jr.res?.scores || []).map((s) => s.id))
    const exact = want.size === got.size && [...want].every((id) => got.has(id))
    if (jr.res && exact) { validJudges.push({ ...jr.res, _tag: jr.job.tag }); judgedOnce.add(jr.job.key) }
    else {
      log(`judge-${jr.job.tag}-${i}: ID不一致/失敗→リトライ`)
      const again = await agent(judgePrompt(jr.job), { label: `judge-${jr.job.tag}-${i}-retry`, phase: P, schema: JUDGE_SCHEMA })
      const got2 = new Set((again?.scores || []).map((s) => s.id))
      if (again && want.size === got2.size && [...want].every((id) => got2.has(id))) {
        validJudges.push({ ...again, _tag: jr.job.tag }); judgedOnce.add(jr.job.key)
      }
    }
  }
  for (const k of judgedOnce) unjudgedCategories.delete(k)

  // --- 系統的失敗の検知（レート制限等の外部要因。イテレーションを浪費せず中断する） ---
  if ((gen === null && gate === null) || (validJudges.length === 0)) {
    interrupted = true
    interruptedAt = i
    log(`iter ${i}: 系統的失敗（gen=${gen ? 'ok' : 'null'} gate=${gate ? 'ok' : 'null'} judges=${validJudges.length}/${judgeJobs.length}）— レート制限等の外部要因とみなし中断。resumeFromRunIdで再開可能`)
    break
  }

  // --- 集計準備（最小値合議） ---
  const allScores = validJudges.flatMap((j) => j.scores)
  const scoreMap = {}
  for (const s of allScores) scoreMap[s.id] = Math.min(scoreMap[s.id] ?? 5, s.score)
  // blockerに安定IDを付与
  const allBlockers = validJudges.flatMap((j, ji) => j.blockers.map((b, bi) => ({ ...b, blockerId: `blk-${ji}-${bi}`, from: j._tag })))

  // --- Audit（敵対監査: 5点・90%カテゴリ全基準・design3-4点・E軸全件。blocker検証・誤測定の再測定差し戻し） ---
  const catPctPre = {}
  for (const [key, cat] of Object.entries(CATEGORIES)) {
    catPctPre[key] = cat.ids.reduce((a, id) => a + (scoreMap[id] ?? 0), 0) / (cat.ids.length * 5)
  }
  const auditTargets = new Set()
  for (const s of allScores) if (s.score === 5) auditTargets.add(s.id)
  for (const [key, cat] of Object.entries(CATEGORIES)) if (catPctPre[key] >= 0.9) cat.ids.forEach((id) => auditTargets.add(id))
  for (const id of CATEGORIES.design.ids) if ((scoreMap[id] ?? 0) >= 3 && (scoreMap[id] ?? 0) <= 4) auditTargets.add(id)
  CATEGORIES.trust.ids.forEach((id) => auditTargets.add(id))

  const audit = await retry(
    (r) => agent(
      `あなたは敵対監査員。審査員パネルの採点の甘さと誤りを暴くのが仕事である。反証は証拠（path:line / スクリーンショット名+縦位置）付きでのみ成立する。

## 審査員パネルの出力（採点+blocker。blockerIdで参照すること）
${JSON.stringify(validJudges.map((j) => ({ tag: j._tag, category: j.category, scores: j.scores })), null, 2)}
blockers: ${JSON.stringify(allBlockers.map((b) => ({ blockerId: b.blockerId, title: b.title, detail: b.detail, evidence: b.evidence })), null, 2)}

## 任務（${RUBRIC} の「Scoring Discipline」に従う）
1. 重点反証対象（${[...auditTargets].join(', ') || 'なし'}）について、アンカー定義に照らして反証を試みる。コード（${TARGET}）とスクリーンショット（${SHOTS}/ のmanifest確認の上、該当スライスを必ずReadで目視）から証拠を集め、アンカーを満たさない点があれば下方修正（adjustments）。特にE軸（E1〜E3）はLP全文（JSON-LD・meta・属性含む）を ${BRIEF} のFacts表と突合する
2. 証拠が曖昧・検証不能・実在しない採点は自ら検証し直し、確認できなければ下方修正
3. 各blockerを検証: ${BRIEF} と突合し、事実誤認（実はブリーフに記載がある等）は valid:false、正当なら valid:true（blockerIdで返す）
4. **低得点の誤測定の検出**: 採点の根拠証拠が事実誤認（指摘箇所が実在しない・ブリーフに記載がある事実を捏造扱い等）である基準は remeasure に挙げる（スコアを上げるのではなく、再測定に差し戻す）
5. 上方修正は禁止

StructuredOutputで {adjustments, blockerVerdicts, remeasure, notes} を返す。`,
      { label: r ? `audit-${i}-retry` : `audit-${i}`, phase: P, schema: AUDIT_SCHEMA }
    ),
    `audit-${i}`
  )

  // 下方修正の適用
  if (audit) {
    for (const adj of audit.adjustments) {
      if (ALL_IDS.includes(adj.id) && adj.to < (scoreMap[adj.id] ?? 5)) scoreMap[adj.id] = Math.max(0, adj.to)
    }
  }
  // 誤測定の再測定（上方修正ではなく測り直し。新しい審査員が確定値を出す）
  const remeasureIds = (audit?.remeasure || []).map((r) => r.id).filter((id) => ALL_IDS.includes(id))
  if (remeasureIds.length) {
    const byCat = {}
    for (const [key, cat] of Object.entries(CATEGORIES)) {
      const hit = cat.ids.filter((id) => remeasureIds.includes(id))
      if (hit.length) byCat[key] = hit
    }
    const remeasured = await parallel(
      Object.entries(byCat).map(([key, ids]) => () =>
        agent(
          `あなたは${CATEGORIES[key].personas[0]}。前任審査員の採点根拠に事実誤認があったため、基準 ${ids.join(', ')} のみを白紙から再採点する（再測定。前任のスコアは見ない）。
${RUBRIC} のアンカーに従い、${TARGET}・${BRIEF}・${SHOTS}/（manifest確認の上、該当箇所をReadで目視）から証拠を集めて採点する。
監査員の指摘（参考。これに迎合せず自分で測ること）: ${JSON.stringify((audit?.remeasure || []).filter((r) => ids.includes(r.id)), null, 2)}
StructuredOutputで category="${key}", scores=[${ids.map((id) => `{id:"${id}",...}`).join(', ')}], blockers, fixes を返す。`,
          { label: `remeasure-${key}-${i}`, phase: P, schema: JUDGE_SCHEMA }
        )
      )
    )
    for (const rm of remeasured.filter(Boolean)) {
      for (const s of rm.scores) if (remeasureIds.includes(s.id)) scoreMap[s.id] = s.score
    }
  }

  // blocker確定（監査でvalid:falseになったものを除外。ID照合）
  const verdictMap = new Map((audit?.blockerVerdicts || []).map((v) => [v.blockerId, v.valid]))
  const liveBlockers = allBlockers.filter((b) => verdictMap.get(b.blockerId) !== false)

  // --- 集計（決定的・コードで実施） ---
  const categories = {}
  let total = 0
  let minCriterion = 5
  for (const [key, cat] of Object.entries(CATEGORIES)) {
    let sum = 0
    for (const id of cat.ids) {
      const v = unjudgedCategories.has(key) ? 0 : (scoreMap[id] ?? 0)
      sum += v
      if (v < minCriterion) minCriterion = v
    }
    categories[key] = { points: sum, max: cat.ids.length * 5, pct: sum / (cat.ids.length * 5) }
    total += sum
  }
  let iterPass =
    gateOk &&
    audit !== null &&
    unjudgedCategories.size === 0 &&
    total >= PASS_TOTAL &&
    minCriterion >= PASS_CRITERION_MIN &&
    Object.values(categories).every((c) => c.pct >= PASS_CATEGORY_PCT) &&
    liveBlockers.length === 0

  // --- PASS候補時の最終再検証（独立エージェントがゲートを再実行。未検証PASSの禁止） ---
  if (iterPass) {
    const confirm = await agent(
      `最終再検証係。修正は禁止。手順:
1. \`bash scripts/lp-capture.sh ${TARGET} ${ITER}/confirm-shots\` を実行
2. \`node scripts/lp-checks.mjs --html ${TARGET} --gate ${GATE} --out ${ITER}/confirm --baseline ${RUN}/baseline-status.txt --shots ${ITER}/confirm-shots\` を実行
3. ${ITER}/confirm/gate.json を読み、pass/failureCount/failures/warnings をそのままStructuredOutputで返す`,
      { label: `confirm-${i}`, phase: P, schema: GATE_SCHEMA }
    )
    if (!confirm || confirm.pass !== true || confirm.failureCount !== 0) {
      iterPass = false
      log(`iter ${i}: 最終再検証でゲート不一致（confirm=${confirm ? confirm.failureCount + '件の失敗' : 'null'}）→PASS取り消し`)
    }
  }

  totals.push(total)
  minCriterions.push(minCriterion)
  gateRedCounts.push(gate ? gate.failureCount : 99)
  blockerCounts.push(liveBlockers.length)

  const agg = {
    runId, slug, iter: i, rubricVersion: '1.1.0', startedAt,
    gate: { pass: gateOk, failures: gate?.failures || [] },
    criteria: scoreMap, categories, total,
    minCriterion,
    unjudgedCategories: [...unjudgedCategories],
    blockers: liveBlockers.map((b) => `[${b.blockerId}] ${b.title}`),
    auditExecuted: audit !== null,
    auditAdjustments: (audit?.adjustments || []).length,
    remeasured: remeasureIds,
    pass: iterPass,
    strategyRevision,
    strategyRevisionReason,
  }
  finalAgg = agg
  timeline.push({ iter: i, total, gateRed: gate ? gate.failureCount : null, blockers: liveBlockers.length, minCriterion, pass: iterPass })
  log(`iter ${i}: total=${total}/100 gateRed=${gate ? gate.failureCount : '?'} blockers=${liveBlockers.length} min=${minCriterion} → ${iterPass ? 'PASS' : 'continue'}`)

  // --- fixlist 構築（blocker/highは無制限、medium/lowは10件まで） ---
  const judgeFixes = validJudges.flatMap((j) => j.fixes)
  const prio = { blocker: 0, high: 1, medium: 2, low: 3 }
  const sorted = judgeFixes.sort((a, b) => (prio[a.priority] ?? 9) - (prio[b.priority] ?? 9))
  const must = sorted.filter((f) => f.priority === 'blocker' || f.priority === 'high')
  const rest = sorted.filter((f) => f.priority !== 'blocker' && f.priority !== 'high').slice(0, 10)
  fixlist = {
    gateFailures: (gate?.failures || []).map((f) => `[${f.id}] ${f.detail}`),
    blockers: liveBlockers.map((b) => `${b.title}: ${b.detail} (証拠: ${b.evidence})`),
    unjudgedCategories: [...unjudgedCategories].map((k) => `カテゴリ${k}が未採点（審査員失敗）— 原因不明の0点はこれ`),
    weakCriteria: Object.entries(scoreMap).filter(([, v]) => v < 4).sort((a, b) => a[1] - b[1]).map(([id, v]) => `${id}=${v}`),
    fixes: [...must, ...rest],
    auditNotes: audit?.notes || '',
  }

  // --- Record（履歴・成果物の永続化。ベースラインも更新） ---
  await retry(
    (r) => agent(
      `記録係。以下を正確に実行する（内容の改変・要約禁止）:
1. ${ITER}/scores.json に次のJSONを書く:\n${JSON.stringify(agg, null, 2)}
2. ${ITER}/judges.json に審査員・監査の生データ（このプロンプト末尾のJUDGES_RAW）をそのまま書く
3. ${ITER}/fixlist.json に次を書く:\n${JSON.stringify(fixlist, null, 2)}
4. \`date -u +%Y-%m-%dT%H:%M:%SZ\` で現在時刻を取得し、lp-system/history.jsonl に {"ts": <取得時刻>, ...scores.jsonと同内容} の1行を **>> で追記**する（既存行の変更禁止）
5. 書いた3ファイルを \`python3 -m json.tool\` で検証し、パース失敗があれば書き直す
6. ${ITER}/snapshot.html が無ければ \`cp ${TARGET} ${ITER}/snapshot.html\`
7. \`git status --porcelain > ${RUN}/baseline-status.txt\` でベースラインを更新する（記録ファイル追加後の状態を次イテレーションのG0基準にする）

JUDGES_RAW:
${JSON.stringify({ judges: validJudges, audit }, null, 2)}`,
      { label: r ? `record-${i}-retry` : `record-${i}`, phase: P, model: 'haiku' }
    ),
    `record-${i}`
  )

  if (iterPass) { passed = true; break }

  // --- 停滞検知（多信号）と早期デザイン改訂 ---
  strategyRevision = false
  strategyRevisionReason = ''
  const remaining = maxIters - i
  if (remaining >= 2) {
    if (i >= 2 && categories.design.pct < 0.6) {
      strategyRevision = true
      strategyRevisionReason = `Visual Design得点率${Math.round(categories.design.pct * 100)}%<60% — 部分修正では脱出困難`
    } else if (i >= 3) {
      const n = totals.length
      const scoreStall = totals[n - 1] - totals[n - 3] < 2
      const gateStall = gateRedCounts[n - 1] >= gateRedCounts[n - 3]
      const blockerStall = blockerCounts[n - 1] >= blockerCounts[n - 3]
      const minStall = minCriterions[n - 1] <= minCriterions[n - 3]
      if (scoreStall && gateStall && blockerStall && minStall) {
        strategyRevision = true
        strategyRevisionReason = '全信号（スコア・ゲート・blocker・最低基準）が2イテレーション停滞'
      }
    }
  }
}

// ---------- 終了 ----------
if (interrupted) {
  log(`INTERRUPTED at iter ${interruptedAt}: 外部要因（レート制限等）による中断。品質判定ではない。`)
} else if (!passed) {
  log(`FAILED_TO_CONVERGE: ${maxIters}イテレーションで合格に至らず。人間のレビューが必要。`)
}
return {
  pass: passed,
  interrupted,
  slug, runId,
  iterations: timeline,
  finalScore: totals.at(-1) ?? 0,
  final: finalAgg,
  runDir: RUN,
  escalation: passed
    ? null
    : interrupted
      ? `INTERRUPTED — iter ${interruptedAt} で外部要因により中断。レート制限リセット後に resumeFromRunId で再開する（品質のFAILではない）`
      : 'FAILED_TO_CONVERGE — runDir内のscores/fixlistを人間がレビューし、ブリーフ改訂またはmaxIters増で再実行する',
}
