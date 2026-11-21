"""追跡ツリーのデータ（JSON）を検証し、雛形に埋め込んで1枚の HTML に書き出す。リポジトリは読み取るだけである。

使い方: python3 build.py TREE_JSON REPO_DIR OUT_HTML
"""
import html
import json
import sys
from pathlib import Path

from validate import EXT, url_for, validate

TEMPLATE = Path(__file__).resolve().parent / 'template.html'


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    tree, repo, out = sys.argv[1:]
    data = json.loads(Path(tree).read_text(encoding='utf-8'))
    errs, _ = validate(data, repo)
    if errs:
        raise SystemExit('データが不正なので書き出さない:\n' + '\n'.join(f'error: {e}' for e in errs))

    for n in data['nodes']:
        if n['t'] == '実装' and 'f' in n and not n['f'].startswith(EXT):
            n['url'] = url_for(data['meta'], n['f'], n['l'])

    page = TEMPLATE.read_text(encoding='utf-8')
    for mark in ('__TITLE__', '__DATA__'):
        if page.count(mark) != 1:
            raise SystemExit(f'雛形の差し込み口 {mark} は1つでなければならない（{page.count(mark)} 個ある）')
    # </script> や <!-- で埋め込みが途切れないよう、< を JSON として同じ意味の \u003c に置き換える
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    page = page.replace('__TITLE__', html.escape(data['meta']['title'])).replace('__DATA__', payload)

    Path(out).write_text(page, encoding='utf-8')
    print(f'{out} を書き出した（{len(page.encode("utf-8")):,} バイト、{len(data["nodes"])} 節）')


if __name__ == '__main__':
    main()
