"""追跡ツリーのデータ（JSON）を、対象リポジトリの固定したコミットに照らして検証する。リポジトリは読み取るだけで、書き込まない。

使い方: python3 validate.py TREE_JSON REPO_DIR
"""
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter

TYPES = ['目的', '要求', '機能', '要件', '仕様', '実装']
PVS = {'確定', '記載', '推定'}
GAP_PVS = {'確認', '推定'}
STATUS_KEYS = {'platform', 'manual', 'none'}
NO_IMPL = '記載のみで、実装は無い。'
EXT = '（外部）'
META_KEYS = {'title', 'repo', 'commit', 'sha', 'status', 'confirmedFiles'}
ALLOWED = {
    'plain': {'id', 'p', 't', 'n', 'pv', 'refs'},
    '仕様': {'id', 'p', 't', 'n', 'pv', 'refs', 'st', 'how', 'gaps'},
    '実装': {'id', 'p', 't', 'k', 'f', 'l', 'q'},
    '外部': {'id', 'p', 't', 'k', 'f', 'q', 'url'},
    '無し': {'id', 'p', 't', 'n'},
}


def span(l):
    m = re.fullmatch(r'(\d+)(?:-(\d+))?', str(l))
    return (int(m[1]), int(m[2] or m[1])) if m else None


def url_for(meta, f, l):
    a, b = span(l)
    return (f'https://github.com/{meta["repo"]}/blob/{meta["sha"]}/{f}' + ('?plain=1' if f.endswith('.md') else '')
            + (f'#L{a}' if a == b else f'#L{a}-L{b}'))


def norm(s):
    s = unicodedata.normalize('NFKC', s)
    return ''.join(c for c in s if not (c.isspace() or unicodedata.category(c)[0] in 'PS'))


def validate(d, repo):
    errs, warns = [], []
    meta, nodes = d['meta'], d['nodes']

    def git(*a):
        return subprocess.check_output(['git', '-C', repo, *a], text=True, stderr=subprocess.DEVNULL)

    # ---- meta ----
    missing = {'title', 'repo', 'commit', 'sha', 'status'} - set(meta)
    if missing or set(meta) - META_KEYS:
        errs.append(f'meta の項目が違う（足りない {sorted(missing)}、余分 {sorted(set(meta) - META_KEYS)}）')
        return errs, warns
    st = meta['status']
    if set(st) != STATUS_KEYS or not all(isinstance(v, dict) and v.get('label') and v.get('desc') for v in st.values()):
        errs.append('meta.status は platform・manual・none の3つで、それぞれ label と desc を持たなければならない')
    try:
        if git('rev-parse', f'{meta["commit"]}^{{commit}}').strip() != meta['sha']:
            errs.append('meta.sha が meta.commit のコミットと一致しない')
        files = set(git('ls-tree', '-r', '-z', '--name-only', meta['sha']).split('\0')) - {''}
    except subprocess.CalledProcessError:
        errs.append(f'コミット {meta["commit"]} が {repo} に無い')
        return errs, warns
    confirmed = set(meta.get('confirmedFiles', []))
    if confirmed - files:
        errs.append(f'meta.confirmedFiles に追跡されていないファイルがある: {sorted(confirmed - files)}')
    raw = json.dumps(d, ensure_ascii=False)
    if re.search(r'/(?:Users|home)/\w', raw) or re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', raw):
        errs.append('ローカルの絶対パスかメールアドレスが含まれる')

    cache = {}

    def lines(f):
        if f not in cache:
            cache[f] = git('show', f'{meta["sha"]}:{f}').splitlines() if f in files else None
        return cache[f]

    def check_range(where, f, l):
        s = span(l)
        if s is None:
            errs.append(f'{where}: 行の書式が違う {f}:{l}（N か N-M）')
            return None
        if lines(f) is None:
            errs.append(f'{where}: 追跡されていないファイル {f}')
            return None
        if not 1 <= s[0] <= s[1] <= len(lines(f)):
            errs.append(f'{where}: 行範囲がファイルの長さを超える {f}:{l}（{len(lines(f))} 行）')
            return None
        return norm(' '.join(lines(f)[s[0] - 1:s[1]]))

    def check_quote(where, f, l, q):
        text = check_range(where, f, l)
        if text is None:
            return
        for part in re.split(r' / |…', q):
            if part.strip() and norm(part) not in text:
                errs.append(f'{where}: 引用がその行に無い {f}:{l} «{part}»')

    # ---- tree ----
    ids = [n['id'] for n in nodes]
    if len(ids) != len(set(ids)):
        errs.append('id が重複している: ' + str([i for i, c in Counter(ids).items() if c > 1]))
    byid = {n['id']: n for n in nodes}
    kids = {}
    for n in nodes:
        kids.setdefault(n['p'], []).append(n)
    roots = kids.get(None, [])
    if len(roots) != 1 or roots[0]['t'] != '目的':
        errs.append('根は p が null・種類「目的」の1つだけでなければならない')

    used = set()
    for n in nodes:
        i, t, ch = n['id'], n['t'], kids.get(n['id'], [])
        if t not in TYPES:
            errs.append(f'{i}: 種類 {t} は使えない')
            continue
        if n['p'] is not None:
            if n['p'] not in byid:
                errs.append(f'{i}: 親 {n["p"]} が無い')
                continue
            parent = byid[n['p']]['t']
            if parent in TYPES and TYPES.index(parent) >= TYPES.index(t):
                errs.append(f'{i}: {t}の親が{parent}で、種類の順（{" → ".join(TYPES)}）に反する')
        if t == '実装':
            if byid.get(n['p'], {}).get('t') != '仕様':
                errs.append(f'{i}: 実装節の親が仕様節でない')
            if ch:
                errs.append(f'{i}: 実装節に子がある')
            kind = '無し' if n.get('n') == NO_IMPL else '外部' if str(n.get('f', '')).startswith(EXT) else '実装'
            if set(n) != ALLOWED[kind]:
                errs.append(f'{i}: 実装節の項目が違う（{kind}の項目は {sorted(ALLOWED[kind])}）')
                continue
            if kind == '無し':
                if len(kids.get(n['p'], [])) != 1:
                    errs.append(f'{i}: 「{NO_IMPL}」は実装の無い仕様のただ1つの子でなければならない')
            elif kind == '外部':
                if not str(n['url']).startswith('https://'):
                    errs.append(f'{i}: 外部の url が https:// で始まらない')
            else:
                check_quote(i, n['f'], n['l'], n['q'])
                used.add(n['f'])
            continue
        # 目的・要求・機能・要件・仕様
        extra = set(n) - ALLOWED['仕様' if t == '仕様' else 'plain']
        if extra or not {'id', 'p', 't', 'n', 'pv'} <= set(n):
            errs.append(f'{i}: 項目が違う（余分 {sorted(extra)}、必須 id・p・t・n・pv）')
            continue
        if not ch:
            errs.append(f'{i}: 子の無い{t}節')
        if t == '仕様':
            if any(c['t'] != '実装' for c in ch):
                errs.append(f'{i}: 仕様の子は実装節だけでなければならない')
            if n.get('st') not in st:
                errs.append(f'{i}: st は {sorted(st)} のどれかを必ず置く')
        if not n['n'].endswith('。'):
            errs.append(f'{i}: 文が「。」で終わらない')
        if n['pv'] not in PVS:
            errs.append(f'{i}: pv {n["pv"]} は使えない')
        if n['pv'] != '推定' and not n.get('refs'):
            errs.append(f'{i}: pv「{n["pv"]}」の節は、出所の refs を1つ以上持つ')
        if n['pv'] == '確定' and not any(r.get('f') in confirmed for r in n.get('refs', [])):
            errs.append(f'{i}: pv「確定」の節は、meta.confirmedFiles にあるファイルの出所を持つ')
        for r in n.get('refs', []):
            if set(r) != {'k', 'f', 'l', 'q'}:
                errs.append(f'{i}: refs の項目は k・f・l・q の4つ')
                continue
            check_quote(i, r['f'], r['l'], r['q'])
            used.add(r['f'])
        for g in n.get('gaps', []):
            if set(g) - {'ty', 'tx', 'pv', 'refs'} or not {'ty', 'tx', 'pv'} <= set(g) or g['pv'] not in GAP_PVS:
                errs.append(f'{i}: gaps の項目が違う（ty・tx・pv は必須で pv は {sorted(GAP_PVS)}、refs は任意）')
                continue
            for s in g.get('refs', []):
                f, _, l = s.rpartition(':')
                check_range(f'{i} gaps', f, l)

    for f in sorted(files - used):
        warns.append(f'一度も参照されないファイル {f}')
    return errs, warns


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    d = json.load(open(sys.argv[1], encoding='utf-8'))
    errs, warns = validate(d, sys.argv[2])
    print('nodes:', dict(Counter(n['t'] for n in d['nodes'])))
    for w in warns:
        print('warning:', w)
    for e in errs:
        print('error:', e)
    print('errors:', len(errs))
    sys.exit(1 if errs else 0)


if __name__ == '__main__':
    main()
