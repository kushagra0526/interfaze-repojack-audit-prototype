"""python -m repojack.cli --org InterfazeAI --old JigsawStack --npm jigsawstack omiai --pypi jigsawstack --hf interfaze-ai --site https://interfaze.ai"""
import argparse
import json
import urllib.request
from collections import Counter
from pathlib import Path

from .resolve import owner_info, resolve
from .scan import SEVERITY_ORDER, Ref, clone_org, ref_pattern, scan_hf, scan_registries, scan_tree, to_json


def scan_site(url, old):
    try:
        html = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "repojack-scan"}),
                                      timeout=20).read().decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return []
    out = []
    for m in ref_pattern(old).finditer(html):
        repo = next((g for g in m.groups() if g), None)
        out.append(Ref(f"site:{url}", "page", m.group(0), repo, m.group(0), "site navigation", "HIGH",
                       "a link on the live website"))
    return out


def run(args):
    work = Path(args.work)
    names = clone_org(args.org, work / "repos")
    refs = []
    for n in names:
        refs += scan_tree(work / "repos" / n, f"github:{args.org}/{n}", args.old)
    refs += scan_registries(args.old, args.npm, args.pypi)
    if args.hf:
        refs += scan_hf(args.hf, args.old)
    for s in args.site:
        refs += scan_site(s, args.old)
    resolve(refs, args.old, args.org)
    owner = owner_info(args.old)
    refs.sort(key=lambda r: (SEVERITY_ORDER.index(r.severity), -r.weight, r.source, r.location))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data = {"org": args.org, "old": args.old, "old_owner_now": owner, "repos_scanned": len(names),
            "by_severity": Counter(r.severity for r in refs), "refs": to_json(refs)}
    (out / "findings.json").write_text(json.dumps(data, indent=1, default=str))
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--npm", nargs="*", default=[])
    ap.add_argument("--pypi", nargs="*", default=[])
    ap.add_argument("--hf", default="")
    ap.add_argument("--site", nargs="*", default=[])
    ap.add_argument("--work", default=".work")
    ap.add_argument("--out", default="out")
    d = run(ap.parse_args())
    print(json.dumps({k: v for k, v in d.items() if k != "refs"}, indent=1, default=str))


if __name__ == "__main__":
    main()
