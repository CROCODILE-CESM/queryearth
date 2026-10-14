"""Rebuild the docs site's version list after one version is published.

The gh-pages branch holds one folder per version: "dev" (main) and one per
release tag (v0.1.0, ...). This writes versions.json (read by the version
menu, newest release first, then dev), a root index.html that redirects
to the newest release and a root llms.txt copied from it, and removes anything
else at the root, such as the files of the single-version site that came before.

Usage: python .github/docs_versions.py SITE_DIR
"""

import json
import re
import shutil
import sys
from pathlib import Path

RELEASE = re.compile(r"v(\d+)\.(\d+)\.(\d+)(.*)")
KEEP = {".git", ".nojekyll", "index.html", "llms.txt", "versions.json", "dev"}


def order(name: str) -> tuple:
    """Newest first; a final release sorts after its pre-releases (v1.0.0rc1)."""
    major, minor, patch, rest = RELEASE.fullmatch(name).groups()
    return int(major), int(minor), int(patch), rest == "", rest


def main(site: Path) -> None:
    releases = sorted(
        (p.name for p in site.iterdir() if p.is_dir() and RELEASE.fullmatch(p.name)),
        key=order,
        reverse=True,
    )
    for path in site.iterdir():
        if path.name not in KEEP and path.name not in releases:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    versions = releases + (["dev"] if (site / "dev").is_dir() else [])
    (site / "versions.json").write_text(json.dumps(versions) + "\n")
    (site / ".nojekyll").touch()
    target = f"{versions[0]}/" if versions else "dev/"
    links = "\n".join(f'    <li><a href="{v}/">{v}</a></li>' for v in versions)
    (site / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>queryearth documentation</title>
  <meta http-equiv="refresh" content="0; url={target}">
  <link rel="canonical" href="{target}">
</head>
<body>
  <p>Redirecting to the <a href="{target}">latest documentation</a>. All versions:</p>
  <ul>
{links}
  </ul>
</body>
</html>
""")
    newest = site / target / "llms.txt"  # language models look for /llms.txt
    if newest.exists():
        shutil.copyfile(newest, site / "llms.txt")
    print("versions:", ", ".join(versions), "->", target)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
