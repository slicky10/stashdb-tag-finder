#!/usr/bin/env python3
"""Read-only StashDB tag search across locally identified Stash scenes.

Authentication: local Stash uses its plugin SessionCookie; StashDB uses its own ApiKey.
No local library contents or fingerprints are uploaded: only already-linked StashDB IDs
are sent in findScene queries.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LOCAL_SCENES = '''query LocalScenes($filter: FindFilterType!) {
  findScenes(filter: $filter) {
    scenes { id title stash_ids { endpoint stash_id } }
  }
}'''
REMOTE_SCENE = '''query RemoteScene($id: ID!) {
  findScene(id: $id) { id title tags { name } }
}'''


def request(endpoint, query, variables, headers):
    payload = json.dumps({'query': query, 'variables': variables}).encode('utf-8')
    req = urllib.request.Request(endpoint, data=payload,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json', **headers}, method='POST')
    with urllib.request.urlopen(req, timeout=35) as resp:
        result = json.load(resp)
    if result.get('errors'):
        # Never log credentials or full request payloads.
        messages = [str(e.get('message', 'GraphQL error')) for e in result['errors']]
        raise ValueError('; '.join(messages)[:250])
    return result['data']


def normalize_endpoint(value):
    return str(value or '').rstrip('/').lower()


def local_stash_endpoint(conn):
    scheme = conn.get('Scheme', 'http')
    host = conn.get('Host', '127.0.0.1')
    # Plugin process usually shares the Stash host network. Prefer explicit host
    # when provided; otherwise 127.0.0.1. Override via STASH_GRAPHQL_URL if needed.
    port = int(conn.get('Port', 9999))
    return os.environ.get('STASH_GRAPHQL_URL') or f'{scheme}://{host}:{port}/graphql'


def main():
    invocation = json.load(sys.stdin)
    args = invocation.get('args') or {}
    cfg = json.loads(Path(__file__).with_name('config.json').read_text(encoding='utf-8'))
    term = str(args.get('search_tag') or cfg.get('stashdb_search_tag') or 'Interracial').strip()
    if not term:
        raise ValueError('Set stashdb_search_tag in config.json')
    conn = invocation['server_connection']
    cookie = conn.get('SessionCookie') or {}
    if not cookie.get('Name') or not cookie.get('Value'):
        raise ValueError('Stash session cookie not available')
    db_endpoint = str(cfg.get('stashdb_endpoint') or 'https://stashdb.org/graphql')
    if normalize_endpoint(db_endpoint) != 'https://stashdb.org/graphql':
        raise ValueError('This plugin currently supports https://stashdb.org/graphql only')
    db_key = os.environ.get('STASHDB_API_KEY') or cfg.get('stashdb_api_key')
    if not db_key:
        raise ValueError('Set STASHDB_API_KEY environment variable or stashdb_api_key in config.json')
    stash_url = local_stash_endpoint(conn)
    local_headers = {'Cookie': f"{cookie['Name']}={cookie['Value']}"}
    remote_headers = {'ApiKey': db_key}
    limit = min(10000, max(1, int(cfg.get('max_scenes', 200))))
    pagesize = 100
    matched = []
    stats = {'searched_local_scenes': 0, 'linked_to_stashdb': 0,
             'remote_scenes_found': 0, 'errors': 0}
    failures = []
    cache = {}
    for page in range(1, (limit + pagesize - 1)//pagesize + 1):
        size = min(pagesize, limit - stats['searched_local_scenes'])
        if size <= 0:
            break
        scenes = request(stash_url, LOCAL_SCENES,
                         {'filter': {'page': page, 'per_page': size}}, local_headers)['findScenes']['scenes']
        if not scenes:
            break
        stats['searched_local_scenes'] += len(scenes)
        for scene in scenes:
            ids = [item['stash_id'] for item in (scene.get('stash_ids') or [])
                   if normalize_endpoint(item.get('endpoint')) == normalize_endpoint(db_endpoint)
                   and item.get('stash_id')]
            if not ids:
                continue
            stats['linked_to_stashdb'] += 1
            for dbid in dict.fromkeys(ids):
                try:
                    if dbid not in cache:
                        cache[dbid] = request(db_endpoint, REMOTE_SCENE, {'id': dbid}, remote_headers).get('findScene')
                        time.sleep(0.5)  # polite pacing
                    remote = cache[dbid]
                    if not remote:
                        continue
                    stats['remote_scenes_found'] += 1
                    tags = [tag['name'] for tag in remote.get('tags', [])]
                    if any(t.casefold() == term.casefold() for t in tags):
                        matched.append({'local_scene_id': scene['id'],
                                        'local_title': scene.get('title'),
                                        'stashdb_id': dbid,
                                        'stashdb_url': 'https://stashdb.org/scenes/' + urllib.parse.quote(dbid, safe=''),
                                        'stashdb_title': remote.get('title'),
                                        'remote_tags': tags})
                    break
                except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as exc:
                    stats['errors'] += 1
                    if len(failures) < 15:
                        failures.append(f"scene {scene['id']}: {type(exc).__name__}: {str(exc)[:180]}")
        if len(scenes) < size:
            break
    # Persist only scan results locally; not API keys or user library contents elsewhere.
    report_path = Path(__file__).with_name('stashdb_tag_results.json')
    report = {'searched_tag': term, 'matched_count': len(matched), 'stats': stats,
              'matches': matched, 'errors_sample': failures}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return {'searched_tag': term, 'matched_count': len(matched), 'stats': stats,
            'matches_preview': matched[:50], 'report_file': str(report_path),
            'errors_sample': failures,
            'note': 'Read-only. Only scenes already linked by StashDB StashID are included; unlinked scenes require identification first.'}


if __name__ == '__main__':
    try:
        print(json.dumps({'output': main()}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'error': f'{type(exc).__name__}: {str(exc)[:300]}'}))
        sys.exit(1)
