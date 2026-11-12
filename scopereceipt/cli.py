"""Command line interface."""
from __future__ import annotations
import argparse
import json
import sys
import zipfile
from pathlib import Path

from .core import ScopeError, read, record_event, render_markdown, report, scan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='scopereceipt', description='Audit what documents your agent actually accessed.')
    parser.add_argument('--state', default='.scopereceipt', help='local receipt directory (default .scopereceipt)')
    sub = parser.add_subparsers(dest='command', required=True)
    scan_cmd = sub.add_parser('scan', help='inventory a file, folder or ZIP')
    scan_cmd.add_argument('source')
    read_cmd = sub.add_parser('read', help='emit content and record observed coverage')
    read_cmd.add_argument('path', help='relative path printed by `scan`')
    read_cmd.add_argument('--start', type=int, default=1, help='first line or page (1-based)')
    read_cmd.add_argument('--end', type=int, help='last line or page (inclusive)')
    report_cmd = sub.add_parser('report', help='print evidence-based coverage')
    report_cmd.add_argument('--format', choices=('md', 'json'), default='md')
    report_cmd.add_argument('--strict', action='store_true', help='exit 1 if anything is incomplete')
    args = parser.parse_args(argv)
    try:
        if args.command == 'scan':
            manifest = scan(args.source, args.state)
            print(f'Inventoried {len(manifest["files"])} files. State: {Path(args.state).resolve()}')
            for file in manifest['files']:
                print(f'  {file["path"]}: {file["kind"]}, {file["units"]} {file["unit_name"]}')
            return 0
        if args.command == 'read':
            content, receipt = read(args.state, args.path, args.start, args.end)
            sys.stdout.write(content)
            sys.stdout.flush()
            record_event(args.state, receipt)
            return 0
        if args.command == 'report':
            result = report(args.state)
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == 'json' else render_markdown(result))
            return 0 if result['status'] == 'COMPLETE' or not args.strict else 1
        return 2
    except (ScopeError, OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f'scopereceipt: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
