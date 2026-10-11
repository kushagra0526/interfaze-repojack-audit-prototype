"""Offline demo on a made-up org: 'old-co' renamed to 'newco', and someone else now holds 'old-co'.

    python demo.py      # → out/report.html, out/patches/, out/findings.json

To audit a real org (read-only), see README: python -m repojack.cli --org ... --old ...
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from repojack.fix import apply  # noqa: E402
from repojack.quickstart import lint  # noqa: E402
from repojack.report import render  # noqa: E402
from repojack.resolve import resolve  # noqa: E402
from repojack.scan import SEVERITY_ORDER, scan_tree, to_json  # noqa: E402

OLD, NEW = "old-co", "newco"
REPOS = {
    "sdk-python": {
        "README.md": "# SDK\n```bash\ngit clone https://github.com/old-co/sdk-python.git\ncd sdk-python\npip install -e .\n```\n"
                     "See also the [JS SDK](https://github.com/Old-Co/sdk-js).\n",
        "setup.py": 'from setuptools import setup\nsetup(name="oldco", url="https://github.com/old-co/sdk-python")\n'},
    "docs": {"docs.json": '{\n  "footer": {"socials": {"github": "https://github.com/old-co"}}\n}\n'},
    "ci-templates": {".github/workflows/release.yml": "jobs:\n  r:\n    steps:\n      - uses: old-co/setup-tool@v1\n"},
    "web-app": {"package.json": '{\n  "name": "web-app",\n  "dependencies": {"utils": "github:old-co/utils#v2"},\n'
                                '  "repository": {"url": "git+https://github.com/old-co/web-app.git"}\n}\n'},
    "starter": {"README.md": "```bash\ngit clone https://github.com/old-co/nextjs-template.git\ncd nextjs-template\n"
                             "cp .env.example .env\n```\n",
                ".gitignore": ".env*\nnode_modules\n"},
}
# what github.com answers today for /old-co/<repo> (made up; the CLI asks GitHub for real)
HEAD = {"/old-co/sdk-python": (301, "https://github.com/newco/sdk-python"),
        "/old-co/sdk-js": (301, "https://github.com/newco/sdk-js"),
        "/old-co/web-app": (301, "https://github.com/newco/web-app"),
        "/old-co/nextjs-template": (301, "https://github.com/newco/starter"),
        "/old-co/utils": (200, ""),                     # the new holder of the name already created it
        "/old-co/setup-tool": (404, "")}                # nothing there yet: claimable right now


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    work = HERE / ".demo"
    shutil.rmtree(work, ignore_errors=True)
    for name, files in REPOS.items():
        for rel, text in files.items():
            p = work / name / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(work / name)], check=True)
        subprocess.run(["git", "-C", str(work / name), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(work / name), "-c", "user.email=d@d", "-c", "user.name=d", "commit", "-qm", "init"], check=True)
    refs = []
    for name in REPOS:
        refs += scan_tree(work / name, f"github:{NEW}/{name}", OLD)
    resolve(refs, OLD, NEW, head=lambda p: HEAD.get(p.lower(), (404, "")))
    refs.sort(key=lambda r: (SEVERITY_ORDER.index(r.severity), r.source, r.location))
    quick = [dict(i, repo=n) for n in REPOS for i in lint(work / n, n)]
    out = HERE / "out"
    shutil.rmtree(out / "patches", ignore_errors=True)
    (out / "patches").mkdir(parents=True, exist_ok=True)
    print(f"\n== {len(refs)} references to '{OLD}' across {len(REPOS)} repos")
    for r in refs:
        print(f"   {r.severity:8s} {r.kind:20s} {r.source.split('/', 1)[1] + '/' + r.location:38s} {r.status}")
    for name in REPOS:
        changed = apply(work / name, refs, OLD, NEW, only_source=f"github:{NEW}/{name}")
        diff = subprocess.run(["git", "-C", str(work / name), "diff"], capture_output=True, text=True).stdout
        if changed:
            (out / "patches" / f"{name}.patch").write_text(diff, encoding="utf-8")
    manual = [r for r in refs if r.repo and not r.status.startswith("REDIRECT")]
    print("\n== left for a person (no redirect target, not rewritten)")
    for r in manual:
        print(f"   {r.source.split('/', 1)[1]}/{r.location}: {r.url} ({r.status})")
    print("\n== quickstart lint")
    for q in quick:
        print(f"   {q['repo']:10s} {q['code']:18s} {q['detail']}")
    data = {"org": NEW, "old": OLD, "repos_scanned": len(REPOS), "refs": to_json(refs),
            "old_owner_now": {"exists": True, "login": OLD, "type": "Organization", "name": "(someone else)",
                              "created_at": "2026-01-01T00:00:00Z", "public_repos": 1, "bio": "(made-up demo)"}}
    (out / "findings.json").write_text(json.dumps({**data, "quickstart": quick}, indent=1))
    (out / "report.html").write_text(render(data, quick, "Old-namespace audit (demo org)"), encoding="utf-8")
    print("\nwrote out/report.html, out/findings.json, out/patches/")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
