#!/usr/bin/env python3
"""StashDB tag search, read-only. Uses Python standard library only."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PLUGIN_ID = 'stashdbTagFinder'
STASHDB_ENDPOINT = 'https://stashdb.org/graphql'
LOCAL_QUERY = '''query($filter: FindFilterType!) {
  findScenes(filter: $filter) { scenes { id title stash_ids { endpoint stash_id } } }
}'''
REMOTE_QUERY = '''query($id: ID!) {
  findScene(id: $id) { id title tags { name } }
}'''
SETTINGS_QUERY = '''query { configuration { plugins } }'''


def graphql(url, query, variables, headers):
    payload = json.dumps({'query': query, 'variables': variables}).encode('utf-8')
    request = urllib.request.Request(url, data=payload, method='POST', headers={
        'Content-Type': 'application/json', 'Accept': 'application/json', **headers})
    with urllib.request.urlopen(request, timeout=35) as response:
        result = json.load(response)
    if result.get('errors'):
        raise ValueError('; '.join(str(e.get('message', 'GraphQL error')) for e in result['errors'])[:300])
    return result['data']


def settings_for(data):
    plugins = (data.get('configuration') or {}).get('plugins') or {}
    if not isinstance(plugins, dict):
        return {}
    values = plugins.get(PLUGIN_ID) or {}
    return values if isinstance(values, dict) else {}


def normalize(url):
    return str(url or '').rstrip('/').lower()


def main():
    invocation = json.load(sys.stdin)
    connection = invocation['server_connection']
    cookie = connection.get('SessionCookie') or {}
    if not cookie.get('Name') or not cookie.get('Value'):
        raise ValueError('Stash plugin session cookie is missing')
    scheme = connection.get('Scheme') or 'http'
    port = int(connection.get('Port') or 9999)
    stash_url = os.environ.get('STASH_GRAPHQL_URL') or f'{scheme}://127.0.0.1:{port}/graphql'
    local_headers = {'Cookie': f"{cookie['Name']}={cookie['Value']}"}

    settings = settings_for(graphql(stash_url, SETTINGS_QUERY, {}, local_headers))
    args = invocation.get('args') or {}
    tag = str(args.get('search_tag') or settings.get('search_tag') or 'Interracial').strip()
    api_key = str(os.environ.get('STASHDB_API_KEY') or settings.get('api_key') or '').strip()
    if not api_key:
        raise ValueError('Set the StashDB API key in Settings > Plugins > StashDB Tag Finder')
    if not tag:
        raise ValueError('Set the search tag in plugin settings')
    max_scenes = min(10000, max(1, int(settings.get('max_scenes') or 200)))
    searched = 0
    linked = 0
    checked_remote = 0
    errors = 0
    matches = []
    cache = {}
    for page in range(1, (max_scenes + 99) // 100 + 1):
        size = min(100, max_scenes - searched)
        if size <= 0:
            break
        data = graphql(stash_url, LOCAL_QUERY, {'filter': {'page': page, 'per_page': 100}}, local_headers)
        scenes = (data.get('findScenes') or {}).get('scenes') or []
        if not scenes:
            break
        for scene in scenes[:size]:
            searched += 1
            ids = [i.get('stash_id') for i in (scene.get('stash_ids') or [])
                   if i.get('stash_id') and normalize(i.get('endpoint')) == STASHDB_ENDPOINT]
            if not ids:
                continue
            linked += 1
            for remote_id in dict.fromkeys(ids):
                try:
                    if remote_id not in cache:
                        cache[remote_id] = graphql(STASHDB_ENDPOINT, REMOTE_QUERY, {'id': remote_id}, {'ApiKey': api_key}).get('findScene')
                        time.sleep(0.35)
                    remote = cache[remote_id]
                    if remote is None:
                        continue
                    checked_remote += 1
                    tags = [t.get('name', '') for t in (remote.get('tags') or [])]
                    if any(t.casefold() == tag.casefold() for t in tags):
                        matches.append({
                            'local_scene_id': scene['id'],
                            'local_title': scene.get('title') or '(untitled)',
                            'stashdb_url': 'https://stashdb.org/scenes/' + urllib.parse.quote(str(remote_id), safe=''),
                            'stashdb_tags': tags
                        })
                    break
                except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as exc:
                    errors += 1
                    print(f"Could not check local scene {scene.get('id')}: {type(exc).__name__}", file=sys.stderr)
        if len(scenes) < 100:
            break

    # Stash logs plugin stderr at INFO so results are visible from its task/log view.
    print(f"StashDB tag '{tag}': {len(matches)} matching scenes; {searched} local scenes checked, "
          f"{linked} linked to StashDB, {errors} lookup errors.", file=sys.stderr)
    for item in matches:
        print(f"MATCH | Stash scene #{item['local_scene_id']} | {item['local_title']} | "
              f"{item['stashdb_url']}", file=sys.stderr)
    return {'searched_tag': tag, 'match_count': len(matches), 'searched_local_scenes': searched,
            'linked_scenes': linked, 'remote_scenes_checked': checked_remote,
            'lookup_errors': errors, 'matches': matches,
            'note': 'Read-only; searches only local scenes already linked to StashDB. No local metadata or files are modified.'}


if __name__ == '__main__':
    try:
        print(json.dumps({'output': main()}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'error': f'{type(exc).__name__}: {str(exc)[:280]}'}))
        sys.exit(1)
