"""Local, observable document-coverage receipts. No claims of model comprehension."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

MAX_FILES = 500
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
MAX_OUTPUT_BYTES = 100 * 1024
SUPPORTED_TEXT = {'.txt', '.md', '.csv', '.json', '.yaml', '.yml', '.py', '.rst', '.xml', '.html', '.log'}
IGNORED_DIRS = {'.git', '.scopereceipt', '.venv', 'venv', '__pycache__', 'node_modules'}


class ScopeError(Exception):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_rel(path: str) -> str:
    """Normalize an archive/member path without accepting traversal or aliases."""
    if '\\' in path or '\x00' in path or ':' in path:
        raise ScopeError(f'unsafe archive path: {path!r}')
    if any(part in ('', '.', '..') for part in path.split('/')):
        raise ScopeError(f'unsafe archive path: {path!r}')
    p = PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or '.' == str(p) or any(not s for s in p.parts):
        raise ScopeError(f'unsafe archive path: {path!r}')
    return p.as_posix()


def _pdf_open(data: bytes):
    try:
        import fitz
    except ImportError as exc:
        raise ScopeError('PDF support requires: pip install "scopereceipt[pdf]"') from exc
    try:
        return fitz.open(stream=data, filetype='pdf')
    except Exception as exc:
        raise ScopeError(f'cannot parse PDF: {exc}') from exc


def _iter_members(source: Path):
    if source.is_dir():
        for root, dirs, files in os.walk(source, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not (Path(root) / d).is_symlink())
            for name in sorted(files):
                f = Path(root) / name
                if f.is_symlink() or not f.is_file():
                    continue
                rel = f.relative_to(source).as_posix()
                if f.stat().st_size > MAX_FILE_BYTES:
                    raise ScopeError(f'file too large: {rel}')
                yield rel, f.read_bytes()
    elif source.is_file() and source.suffix.lower() == '.zip':
        with zipfile.ZipFile(source) as zf:
            members = [i for i in zf.infolist() if not i.is_dir()]
            if len(members) > MAX_FILES:
                raise ScopeError(f'too many archive members ({len(members)})')
            for item in members:
                rel = _safe_rel(item.filename)
                if item.file_size > MAX_FILE_BYTES or (item.compress_size and item.file_size / item.compress_size > 200):
                    raise ScopeError(f'archive member too large or compressed unusually: {rel}')
                with zf.open(item) as stream:
                    data = stream.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    raise ScopeError(f'archive member too large: {rel}')
                yield rel, data
    elif source.is_file():
        if source.stat().st_size > MAX_FILE_BYTES:
            raise ScopeError('file too large')
        yield source.name, source.read_bytes()
    else:
        raise ScopeError(f'input not found: {source}')


def _kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == '.pdf':
        return 'pdf'
    if suffix in SUPPORTED_TEXT:
        return 'text'
    return 'unsupported'


def _describe(path: str, data: bytes) -> dict[str, Any]:
    kind = _kind(path)
    info = {'path': path, 'kind': kind, 'bytes': len(data), 'sha256': _sha(data), 'units': 0, 'unit_name': 'none', 'issue': None}
    if kind == 'text':
        try:
            content = data.decode('utf-8-sig')
            info.update(units=len(content.splitlines(keepends=True)), unit_name='lines')
        except UnicodeDecodeError:
            info.update(kind='unsupported', issue='non-UTF-8 text; explicit conversion required')
    elif kind == 'pdf':
        try:
            with _pdf_open(data) as doc:
                info.update(units=len(doc), unit_name='pages')
        except ScopeError as exc:
            info.update(kind='unsupported', issue=str(exc))
    else:
        info['issue'] = 'unsupported file type'
    return info


def _state_paths(state: Path) -> tuple[Path, Path]:
    return state / 'manifest.json', state / 'events.jsonl'


def scan(source: str | Path, state: str | Path) -> dict[str, Any]:
    source, state = Path(source).expanduser().resolve(), Path(state).expanduser().resolve()
    if source == state or (source.is_dir() and source in state.parents and state.name != '.scopereceipt'):
        # Keeping state under source is OK because .scopereceipt is ignored.
        raise ScopeError('state inside source must be named .scopereceipt')
    entries, seen, total_bytes = [], set(), 0
    for rel, data in _iter_members(source):
        if rel in seen:
            raise ScopeError(f'duplicate path: {rel}')
        seen.add(rel)
        total_bytes += len(data)
        if len(seen) > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
            raise ScopeError('document set exceeds configured limits')
        entries.append(_describe(rel, data))
    if not entries:
        raise ScopeError('no files found')
    manifest = {
        'version': 1,
        'run_id': uuid4().hex,
        'source_type': 'dir' if source.is_dir() else ('zip' if source.suffix.lower() == '.zip' else 'file'),
        'source_path': str(source),
        'scanned_at': datetime.now(timezone.utc).isoformat(),
        'files': entries,
    }
    state.mkdir(parents=True, exist_ok=True)
    manifest_path, events_path = _state_paths(state)
    tmp = manifest_path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(manifest_path)
    events_path.write_text('', encoding='utf-8')  # Start a new bounded run.
    return manifest


def _load(state: str | Path) -> tuple[dict[str, Any], Path]:
    state = Path(state).expanduser().resolve()
    manifest_path, _ = _state_paths(state)
    try:
        return json.loads(manifest_path.read_text(encoding='utf-8')), state
    except FileNotFoundError as exc:
        raise ScopeError('no manifest; run `scopereceipt scan PATH` first') from exc


def _source_bytes(manifest: dict[str, Any], rel: str) -> bytes:
    source = Path(manifest['source_path'])
    if manifest['source_type'] == 'dir':
        # Inventory-relative only, no path escape and no symbolic-link traversal.
        rel = _safe_rel(rel)
        target = source.joinpath(*PurePosixPath(rel).parts)
        if not target.resolve().is_relative_to(source.resolve()) or target.is_symlink():
            raise ScopeError('path escapes inventory root')
        if not target.is_file() or target.stat().st_size > MAX_FILE_BYTES:
            raise ScopeError(f'missing or oversized file: {rel}')
        return target.read_bytes()
    if manifest['source_type'] == 'zip':
        with zipfile.ZipFile(source) as zf:
            names = [i for i in zf.infolist() if i.filename == rel and not i.is_dir()]
            if len(names) != 1 or names[0].file_size > MAX_FILE_BYTES:
                raise ScopeError(f'missing or oversized archive file: {rel}')
            with zf.open(names[0]) as stream:
                return stream.read(MAX_FILE_BYTES + 1)
    if source.name != rel or source.stat().st_size > MAX_FILE_BYTES:
        raise ScopeError('file changed or missing')
    return source.read_bytes()


def read(state: str | Path, rel: str, start: int = 1, end: int | None = None) -> tuple[str, dict[str, Any]]:
    manifest, state_path = _load(state)
    items = {item['path']: item for item in manifest['files']}
    if rel not in items:
        raise ScopeError(f'{rel!r} was not in the scan inventory')
    entry = items[rel]
    if entry['kind'] == 'unsupported':
        raise ScopeError(entry['issue'] or 'unsupported format')
    data = _source_bytes(manifest, rel)
    if _sha(data) != entry['sha256']:
        raise ScopeError('source changed after scan: scan again; stale receipts are invalid')
    if start < 1 or (end is not None and end < start):
        raise ScopeError('invalid range')
    total = entry['units']
    if total == 0:
        raise ScopeError('file has no readable units')
    end = min(total, end if end is not None else (start if entry['kind'] == 'pdf' else start + 79))
    if start > total:
        raise ScopeError(f'start exceeds {total} {entry["unit_name"]}')
    observed = []
    if entry['kind'] == 'text':
        lines = data.decode('utf-8-sig').splitlines(keepends=True)
        content = ''.join(lines[start - 1:end])
        observed = list(range(start, end + 1))
    else:
        chunks = []
        with _pdf_open(data) as doc:
            for page_num in range(start, end + 1):
                text = doc[page_num - 1].get_text('text')
                if text.strip():
                    observed.append(page_num)
                    chunks.append(f'--- page {page_num} (extracted text only) ---\n{text}\n')
                else:
                    chunks.append(f'--- page {page_num}: no extractable text; visual/OCR check required ---\n')
        content = ''.join(chunks)
    if len(content.encode('utf-8')) > MAX_OUTPUT_BYTES:
        raise ScopeError('read result exceeds 100 KiB; request a smaller range')
    event = {
        'run_id': manifest.get('run_id'),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'path': rel, 'sha256': entry['sha256'], 'kind': entry['kind'],
        'requested_start': start, 'requested_end': end, 'observed_units': observed,
        'note': 'access recorded; comprehension not verified; PDF images/figures not inspected',
    }
    return content, event


def record_event(state: str | Path, event: dict[str, Any]) -> None:
    manifest, _ = _load(state)
    if event.get('run_id') != manifest.get('run_id'):
        raise ScopeError('scan changed during read; receipt was not recorded')
    _, events_path = _state_paths(Path(state).expanduser().resolve())
    # This record only states that content was emitted through this tool.
    with events_path.open('a', encoding='utf-8') as out:
        out.write(json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n')


def report(state: str | Path) -> dict[str, Any]:
    manifest, state_path = _load(state)
    _, events_path = _state_paths(state_path)
    events = []
    if events_path.is_file():
        for line in events_path.read_text(encoding='utf-8').splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                raise ScopeError('invalid event log')
    seen = {}
    for event in events:
        if not isinstance(event, dict):
            raise ScopeError('invalid event log')
        if event.get('run_id') != manifest.get('run_id'):
            continue
        key = (event.get('path'), event.get('sha256'), event.get('kind'))
        seen.setdefault(key, set()).update(x for x in event.get('observed_units', []) if isinstance(x, int))
    expected_paths = {entry['path'] for entry in manifest['files']}
    current_paths = set()
    inventory_error = None
    try:
        total_bytes = 0
        for path, data in _iter_members(Path(manifest['source_path'])):
            if path in current_paths:
                raise ScopeError(f'duplicate path: {path}')
            current_paths.add(path)
            total_bytes += len(data)
            if len(current_paths) > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
                raise ScopeError('document set exceeds configured limits')
    except (ScopeError, OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        inventory_error = str(exc)
    added_files = sorted(current_paths - expected_paths)
    removed_files = sorted(expected_paths - current_paths)
    files, covered_files, readable_files, total_units, covered_units = [], 0, 0, 0, 0
    for entry in manifest['files']:
        path, kind, expected = entry['path'], entry['kind'], entry['units']
        changed = False
        try:
            changed = _sha(_source_bytes(manifest, path)) != entry['sha256']
        except (ScopeError, FileNotFoundError, OSError, KeyError, zipfile.BadZipFile):
            changed = True
        covered_set = set() if changed else seen.get((path, entry['sha256'], kind), set())
        visited = sum(1 for i in range(1, expected + 1) if i in covered_set)
        supported = kind in ('text', 'pdf')
        complete = supported and not changed and visited == expected
        if complete:
            covered_files += 1
        if supported:
            readable_files += 1
            total_units += expected
            covered_units += visited
        files.append({
            'path': path, 'kind': kind, 'units': expected, 'visited_units': visited,
            'complete': complete, 'changed': changed,
            'unit_name': entry['unit_name'],
            'missing_ranges': _missing_ranges(expected, covered_set),
            'issue': 'source changed since scan' if changed else entry.get('issue'),
        })
    all_complete = (covered_files == len(files) and len(files) > 0
                    and not added_files and not removed_files and inventory_error is None)
    return {
        'run_id': manifest.get('run_id'),
        'status': 'COMPLETE' if all_complete else 'INCOMPLETE',
        'scope': 'observable content access only; not comprehension or visual inspection',
        'file_count': len(files), 'covered_files': covered_files,
        'readable_files': readable_files, 'total_units': total_units,
        'covered_units': covered_units, 'files': files,
        'added_files': added_files, 'removed_files': removed_files,
        'inventory_error': inventory_error,
    }


def _missing_ranges(total: int, covered: set[int]) -> list[list[int]]:
    ranges = []
    start = None
    for unit in range(1, total + 2):
        if unit <= total and unit not in covered:
            if start is None:
                start = unit
        elif start is not None:
            ranges.append([start, unit - 1])
            start = None
    return ranges


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f'# ScopeReceipt: {result["status"]}',
        '',
        f'Files covered: **{result["covered_files"]}/{result["file_count"]}**',
        f'Observed units: **{result["covered_units"]}/{result["total_units"]}**',
        '',
        '| File | Format | Observed | Missing ranges | Status |',
        '| --- | --- | ---: | --- | --- |',
    ]
    for file in result['files']:
        status = 'complete' if file['complete'] else ('changed' if file['changed'] else 'incomplete')
        path = file['path'].replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
        missing = ', '.join(str(a) if a == b else f'{a}-{b}' for a, b in file['missing_ranges']) or '-'
        lines.append(f'| {path} | {file["kind"]} | {file["visited_units"]}/{file["units"]} | {missing} | {status} |')
    for key, label in [('added_files', 'Added since scan'), ('removed_files', 'Removed since scan')]:
        if result.get(key):
            lines += ['', f'{label}: ' + ', '.join(result[key]) + '. Rescan required.']
    if result.get('inventory_error'):
        lines += ['', 'Inventory check failed: ' + result['inventory_error']]
    lines += ['', '> Evidence of text emitted by ScopeReceipt, not proof of client delivery or understanding. PDF visuals are not checked.', '']
    return '\n'.join(lines)
