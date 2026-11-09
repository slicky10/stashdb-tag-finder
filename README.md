# StashDB Tag Finder — Plugin Manager repository

Read-only Stash plugin that finds **scenes already in your local library** whose linked StashDB scene includes an exact tag such as `Interracial`. No video files, local tags or metadata are edited.

## Publish with GitHub Pages

1. Create a **public** GitHub repository (for example `stashdb-tag-finder`). Upload **all files and folders in this repository**, including `.github/workflows/pages.yml`, to its `main` branch. Do not upload only the ZIP.
2. In GitHub repository **Settings → Pages → Build and deployment**, choose **GitHub Actions**.
3. In the **Actions** tab, run **Publish Stash Plugin Source** if it did not run automatically. Wait for a successful deployment.
4. Your Stash source URL is `https://YOUR-GITHUB-USERNAME.github.io/YOUR-REPOSITORY-NAME/main/index.yml` (replace both placeholders).
5. Open Stash → **Settings → Plugins → Available Plugins → Add Source**. Paste that URL and select a unique local path, for example `stashdb-tags`.
6. Install **StashDB Tag Finder** from Available Plugins.
7. Under **Installed Plugins**, open StashDB Tag Finder's settings. Enter your **StashDB API key**, **Tag to find** (e.g. `Interracial`), and optional **Maximum local scenes**. Save. Do not commit your API key to GitHub.
8. Run **Find my scenes with a StashDB tag** from Stash's Tasks page. View matching local scene IDs, titles and StashDB links in Stash's logs/task output.

Stash requires Python 3 available as `python3` to the Stash server (including inside a Docker container). Only scenes previously identified and linked to StashDB through their StashIDs are searched. The default limit is 200 local scenes; increase it in plugin settings if required. StashDB can require authentication and remote searches may take time for larger libraries.

## How package publication works

`build.py` creates `_site/main/index.yml` and `_site/main/stashdbTagFinder.zip`. The index points to the ZIP and contains its SHA-256 checksum. The ZIP contains the plugin YAML and Python script **at the root**, as required by Stash's package manager.

For local testing run `python build.py`. The `_site` folder is generated and should not be committed. A plugin update should increase the version in both `plugins/stashdbTagFinder/stashdbTagFinder.yml` and `build.py`.

## Security and limitations

- API key is stored in your Stash configuration through the plugin settings UI, **not in the public GitHub repository**.
- Only linked StashDB scene IDs are sent to StashDB; the plugin does not upload videos or scene fingerprints.
- The task is **read-only**. It does not add tags, move files, or change scenes.
- Results appear in Stash task logs. There is not yet a custom interactive in-Stash search panel.
- Python syntax and package checks can be performed offline; live compatibility still requires testing with your Stash server and StashDB API key.
