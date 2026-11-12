"""Cross-platform demo using synthetic fixtures and real CLI exit codes.

Run from the repository root: python scripts/demo.py
Regenerate the README graphic: python scripts/demo.py --svg docs/demo.svg
"""
import argparse
import html
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--svg', type=Path, help='save a graphic of these actual demo results')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='scopereceipt-demo-') as temp:
        state = str(Path(temp) / 'receipts')

        def cli(*arguments, expected=0):
            command = [sys.executable, '-m', 'scopereceipt', '--state', state, *arguments]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding='utf-8', timeout=20)
            if result.returncode != expected:
                raise RuntimeError(f'{arguments}: expected exit {expected}, got {result.returncode}: {result.stderr}')
            return result.stdout

        cli('scan', str(ROOT / 'examples'))
        cli('read', 'contract.txt', '--start', '1', '--end', '2')
        before = json.loads(cli('report', '--format', 'json', '--strict', expected=1))
        print('PARTIAL READ: strict check exits 1')
        print(cli('report'))
        cli('read', 'contract.txt', '--start', '3', '--end', '3')
        cli('read', 'notes.md', '--start', '1', '--end', '3')
        after = json.loads(cli('report', '--format', 'json', '--strict'))
        print('REMAINING TEXT READ: strict check exits 0')
        print(cli('report'))
        if args.svg:
            args.svg.parent.mkdir(parents=True, exist_ok=True)
            panels = []
            for x, result, color, label in [(32, before, '#fbad63', '01  PARTIAL READ'),
                                             (490, after, '#6ee7b7', '02  REMAINING TEXT READ')]:
                rows = []
                for index, item in enumerate(result['files']):
                    y = 255 + index * 46
                    rows.append(f'<text x="{x+24}" y="{y}" fill="#cad5e2" font-size="15">'
                                f'{html.escape(item["path"])}'
                                f'<tspan x="{x+322}">{item["visited_units"]}/{item["units"]}</tspan></text>')
                panels.append(f'''<rect x="{x}" y="122" width="438" height="246" rx="16" fill="#162231"/>
<text x="{x+24}" y="157" fill="#a7b6ca" font-size="13">{label}</text>
<text x="{x+24}" y="199" fill="{color}" font-size="29" font-weight="700">{result['status']}</text>
<text x="{x+24}" y="224" fill="#a7b6ca" font-size="14">{result['covered_units']}/{result['total_units']} text lines emitted</text>
{''.join(rows)}
<text x="{x+24}" y="341" fill="{color}" font-size="14">strict check: exit {1 if result['status']=='INCOMPLETE' else 0}</text>''')
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="440" viewBox="0 0 960 440" role="img" aria-labelledby="title desc">
<title id="title">ScopeReceipt: partial reads fail, complete text coverage passes</title>
<desc id="desc">Actual CLI demo with synthetic fixtures. Two of six lines: incomplete. Six of six: complete. Does not prove understanding.</desc>
<rect width="960" height="440" rx="20" fill="#0c141f"/>
<g font-family="Segoe UI,Arial,sans-serif">
<text x="32" y="51" fill="#f0f5fc" font-size="29" font-weight="700">ScopeReceipt</text>
<text x="32" y="86" fill="#a7b6ca" font-size="18">Your AI says it read everything. Ask for the receipt.</text>
{''.join(panels)}
<text x="32" y="408" fill="#a7b6ca" font-size="14">Real CLI output · Synthetic documents · Access coverage is not understanding</text>
</g></svg>'''
            args.svg.write_text(svg, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
