#!/usr/bin/env python3
"""Create GitHub Pages site with a Stash Plugin Manager index and hashed package."""
import datetime
import hashlib
import pathlib
import shutil
import zipfile

root = pathlib.Path(__file__).resolve().parent
source = root / 'plugins' / 'stashdbTagFinder'
out = root / '_site' / 'main'
if (root / '_site').exists():
    shutil.rmtree(root / '_site')
out.mkdir(parents=True)
package = out / 'stashdbTagFinder.zip'
with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as z:
    for file in sorted(source.iterdir()):
        if file.is_file() and file.suffix in ('.py', '.yml', '.md'):
            z.write(file, arcname=file.name)
checksum = hashlib.sha256(package.read_bytes()).hexdigest()
date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
(out / 'index.yml').write_text(
    '- id: stashdbTagFinder\n'
    '  name: StashDB Tag Finder\n'
    '  version: 0.3.0\n'
    f'  date: "{date}"\n'
    '  path: stashdbTagFinder.zip\n'
    f'  sha256: {checksum}\n'
    '  metadata:\n'
    '    description: Read-only search of your local scenes by their StashDB tags.\n',
    encoding='utf-8')
print(f'Built {package} sha256={checksum}')
