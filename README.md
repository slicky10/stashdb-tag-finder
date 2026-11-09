# Stash Smart Organizer — starter plugin

A conservative Python plugin for Stash. It reads local sidecar JSON metadata, optionally infers missing titles from filenames, updates Stash scenes via GraphQL, and plans or applies file organization.

## Install

1. Install Python 3 on the **machine/container running Stash** and ensure `python3` is on PATH. Windows users can change `python3` in YAML to an accessible Python executable.
2. Copy the whole `stash-smart-organizer` folder into the Stash `plugins` directory.
3. Edit `config.json` to set absolute `library_root` and `destination_root`. For Docker, use paths *inside the Stash container*. The destination must remain inside the library root.
4. In Stash, open **Settings > Plugins > Reload Plugins**.
5. Back up Stash's database and media library. Start with **Preview metadata updates** or **Preview file organization** from the Tasks page.
6. After reviewing proposed results, run **Apply metadata updates**. For actual file moves, set `allow_move` to `true` and run **Apply file organization** only after backing up.

## Sidecar format

Place `My Video.json` alongside `My Video.mp4`:

```json
{"title":"My Video","date":"2024-02-17","details":"Optional description"}
```

The plugin updates **missing** metadata by default. `overwrite_metadata` can enable overwrites. Supported fields: title, date, details. It does not scrape websites automatically. Use Stash's existing Identify/scraper tasks to fetch online metadata; a custom provider adapter can be implemented later.

## Folder naming

`Organized/<Studio>/<Year>/<Title> [scene-id].mp4`

Moves are designed to avoid filename collisions and remain within the library root. Multi-file scenes are skipped. Moves use copy-then-delete for broad filesystem compatibility (which needs sufficient free disk space), and schedule a Stash scan afterwards. Note: this starter does not move sidecars or related external files and does not automatically clean stale file records. Do not run Clean until the post-move scan is verified. For a large or production library, prefer testing on a separate small library first and extending handling for companions and interruptions.

## Caveats

- No external metadata provider has been selected, so online fetching is not yet implemented.
- No live Stash environment was available for end-to-end integration testing.
- Scene query is deliberately capped by `max_scenes`; increase when ready.
- When scenes are moved, Stash may need manual reconciliation depending on version and scan behavior.
- Private media and cookies stay local to Stash; no third-party metadata requests are made.


## NEW: Find your local scenes with a StashDB tag (v0.2.0)

Run **Find my scenes with a StashDB tag** from Stash's plugin tasks.

1. Obtain your StashDB API key from your account on https://stashdb.org.
2. Configure StashDB in Stash under **Settings → Metadata Providers → Stash-box Endpoints**.
3. In `config.json`, set `stashdb_search_tag` to `Interracial` (or another exact StashDB tag name). For authentication, preferably set the `STASHDB_API_KEY` environment variable of the Stash process; alternatively set `stashdb_api_key` in `config.json` and restrict file permissions.
4. Run the plugin task. Look at the task output and the `stashdb_tag_results.json` report saved in the plugin directory. The task only **reads** Stash and StashDB; it never modifies tags or files.

**Matching constraints:** Only local scenes already assigned a StashDB StashID (usually through the Stash scene Tagger) are checked. This conservative implementation does not guess from titles and does not upload file fingerprints. If many local scenes have no StashDB StashID, identify them first via the Stash Scene Tagger. In StashDB, tags are community-contributed and may be incomplete. Search uses case-insensitive **exact tag-name equality**; it is not substring/alias matching. `max_scenes` determines how many local scenes are searched (default 200). For large libraries, increase it. The plugin produces a new report each time; older reports are overwritten.

**Privacy:** The plugin sends only existing linked StashDB scene identifiers to the StashDB API. It does not transmit your local filenames or media files. A report containing local scene titles and IDs is written into the plugin directory.

**Docker:** The Python plugin process must reach the local Stash GraphQL service. If not, define `STASH_GRAPHQL_URL` for the plugin's environment to point to the actual Stash service (for example `http://stash:9999/graphql`).
