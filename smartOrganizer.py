#!/usr/bin/env python3
"""Stash task plugin: safe local sidecar enrichment + optional physical file moves."""
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

QUERY = '''query SmartOrganizerScenes($filter: FindFilterType!) {
  findScenes(filter: $filter) {
    scenes { id title details date studio { name } files { path } }
  }
}'''
UPDATE = '''mutation SmartOrganizerUpdate($input: SceneUpdateInput!) {
  sceneUpdate(input: $input) { id }
}'''
SCAN = '''mutation SmartOrganizerScan($input: ScanMetadataInput!) {
  metadataScan(input: $input)
}'''


def clean(value, fallback="Unknown"):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value or '')).strip().strip('. ')
    return value[:90] or fallback


def gql(endpoint, cookie, query, variables):
    req = urllib.request.Request(endpoint, data=json.dumps({'query': query, 'variables': variables}).encode('utf-8'), headers={'Content-Type': 'application/json', 'Cookie': cookie}, method='POST')
    with urllib.request.urlopen(req, timeout=45) as response:
        result = json.load(response)
    if result.get('errors'):
        raise RuntimeError(str(result['errors'])[:500])
    return result['data']


def within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def metadata_patch(scene, file, config):
    sidecar = file.with_suffix('.json')
    data = {}
    if sidecar.is_file():
        obj = json.loads(sidecar.read_text(encoding='utf-8'))
        if not isinstance(obj, dict):
            raise ValueError('Sidecar must contain a JSON object')
        data = obj
    patch = {}
    if config.get('overwrite_metadata') or not scene.get('title'):
        title = data.get('title') or (file.stem.replace('_', ' ').replace('.', ' ') if config.get('filename_fallback', True) else '')
        if title:
            patch['title'] = str(title)[:300]
    if (config.get('overwrite_metadata') or not scene.get('date')) and isinstance(data.get('date'), str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', data['date']):
        patch['date'] = data['date']
    if (config.get('overwrite_metadata') or not scene.get('details')) and isinstance(data.get('details'), str):
        patch['details'] = data['details'][:10000]
    return patch


def organize(scene, file, config, dry_run):
    root = Path(config['library_root']).expanduser().resolve(strict=True)
    dest_root = Path(config['destination_root']).expanduser().resolve(strict=False)
    source = file.resolve(strict=True)
    if not within(source, root) or not within(dest_root, root) or source.is_symlink():
        return 'SKIP: file or destination outside library root'
    if len(scene.get('files') or []) != 1:
        return 'SKIP: scene has multiple files'
    studio = clean((scene.get('studio') or {}).get('name'))
    year = str(scene.get('date') or '')[:4]
    year = year if re.fullmatch(r'\d{4}', year) else 'Undated'
    title = clean(scene.get('title') or file.stem)
    dest = dest_root / studio / year / (title + ' [' + str(scene['id']) + ']' + file.suffix.lower())
    if source == dest:
        return 'SKIP: already organized'
    if dest.exists():
        return 'SKIP: destination exists'
    if dry_run:
        return 'PLAN: ' + str(source) + ' -> ' + str(dest)
    if not config.get('allow_move', False):
        return 'SKIP: allow_move is false in config.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite an existing destination, even if created after the earlier check.
    with source.open('rb') as src, dest.open('xb') as out:
        shutil.copyfileobj(src, out, 4 * 1024 * 1024)
        out.flush()
        os.fsync(out.fileno())
    if source.stat().st_size != dest.stat().st_size:
        dest.unlink(missing_ok=True)
        raise IOError('Copy size mismatch; source preserved')
    shutil.copystat(source, dest)
    source.unlink()
    return 'MOVED: ' + str(source) + ' -> ' + str(dest)


def main():
    inp = json.load(sys.stdin)
    args = inp.get('args') or {}
    mode = args.get('mode', 'metadata')
    if mode == 'stashdb_tags':
        from stashdb_tag_search import main as tag_main
        return tag_main()
    if mode not in ('metadata', 'organize'):
        raise ValueError('Unrecognized mode')
    dry_run = str(args.get('dry_run', True)).lower() != 'false'
    config_path = Path(__file__).with_name('config.json')
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    conn = inp['server_connection']
    cookie_info = conn.get('SessionCookie') or {}
    cookie = cookie_info.get('Name', '') + '=' + cookie_info.get('Value', '')
    if not cookie_info.get('Name') or not cookie_info.get('Value'):
        raise ValueError('Session cookie unavailable; authenticated Stash connection required')
    scheme = conn.get('Scheme', 'http')
    port = int(conn.get('Port', 9999))
    endpoint = f'{scheme}://127.0.0.1:{port}/graphql'
    max_scenes = max(1, min(int(cfg.get('max_scenes', 200)), 10000))
    logs = []
    changed = 0
    page = 1
    while (page - 1) * 100 < max_scenes:
        batch_size = min(100, max_scenes - (page - 1) * 100)
        scenes = gql(endpoint, cookie, QUERY, {'filter': {'page': page, 'per_page': batch_size}})['findScenes']['scenes']
        if not scenes:
            break
        for scene in scenes:
            paths = scene.get('files') or []
            if not paths:
                continue
            file = Path(paths[0]['path'])
            try:
                if mode == 'metadata':
                    patch = metadata_patch(scene, file, cfg)
                    if not patch:
                        continue
                    if not dry_run:
                        gql(endpoint, cookie, UPDATE, {'input': {'id': scene['id'], **patch}})
                    changed += 1
                    logs.append(('PLAN' if dry_run else 'UPDATED') + f" metadata for scene {scene['id']}: {list(patch)}")
                else:
                    message = organize(scene, file, cfg, dry_run)
                    logs.append(message)
                    if message.startswith('PLAN:') or message.startswith('MOVED:'):
                        changed += 1
            except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
                logs.append(f"ERROR scene {scene['id']}: {exc}")
        if len(scenes) < batch_size:
            break
        page += 1
    # Schedule a library scan after moves so Stash rediscovers the new paths.
    if mode == 'organize' and not dry_run and any(x.startswith('MOVED:') for x in logs):
        try:
            gql(endpoint, cookie, SCAN, {'input': {}})
            logs.append('Scan requested; check Stash task status. Do not run Clean until verified.')
        except Exception as exc:
            logs.append(f'WARNING: Could not start scan: {exc}. Run a manual scan before Clean.')
    return {'mode': mode, 'dry_run': dry_run, 'changed_or_planned': changed, 'messages': logs[:300], 'truncated': len(logs) > 300}


if __name__ == '__main__':
    try:
        print(json.dumps({'output': main()}))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
