"""Find references to a GitHub namespace you no longer own, and rank how dangerous each one is.

After an organization is renamed, GitHub redirects old repository URLs until someone claims the old
name and creates a repository with the same name: then the redirect is overridden and the old URL
serves *their* code (GitHub docs, "Renaming an organization"). Every place that still says the old
name is a door that can be quietly reassigned.

Read-only: clones public repos, reads public registry metadata, sends one GET per referenced URL.
"""
import json
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", "__pycache__", ".venv", "venv"}
TEXT_EXT = {".md", ".mdx", ".txt", ".json", ".toml", ".cfg", ".py", ".ts", ".tsx", ".js", ".jsx", ".yml",
            ".yaml", ".sh", ".ipynb", ".html", ".rst", "", ".lock", ".gitmodules"}
SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


@dataclass
class Ref:
    source: str               # e.g. "github:InterfazeAI/sob" or "pypi:jigsawstack"
    location: str             # file:line or metadata field
    url: str                  # the old-namespace URL as written
    repo: str | None          # repo name under the old namespace (None = the profile itself)
    context: str              # the line
    kind: str = ""
    severity: str = ""
    why: str = ""
    status: str = ""          # REDIRECT -> target | HIJACKED | DANGLING | PROFILE_CLAIMED
    fix_to: str = ""
    weight: int = 0           # monthly downloads for registry refs


def ref_pattern(old):
    o = re.escape(old)
    return re.compile(
        rf"(?i)(?:https?://)?(?:www\.)?(?:github\.com[/:]|raw\.githubusercontent\.com/){o}(?![A-Za-z0-9-])(?:/([A-Za-z0-9_.-]+))?"
        rf"|(?<![\w/.-])github:{o}/([A-Za-z0-9_.-]+)"
        rf"|uses:\s*{o}/([A-Za-z0-9_.-]+)")


def classify(path, line):
    """(kind, severity, why) from where the reference sits and what the line does."""
    p, l = path.lower(), line.strip().lower()
    name = Path(p).name
    if name == ".gitmodules" or "uses:" in l and ".github/workflows" in p:
        return "auto-executed", "CRITICAL", "fetched and run automatically (submodule / GitHub Action)"
    if re.search(r"git\+https?://github|github:", l) and name in {"package.json", "requirements.txt",
                                                                     "pyproject.toml", "setup.py", "setup.cfg"} \
            and not re.search(r'"(url|homepage)"\s*:|url\s*=', l):
        return "dependency", "CRITICAL", "installed as a dependency straight from the old namespace"
    if re.search(r"raw\.githubusercontent\.com", l) and re.search(r"curl|wget|bash|sh\b|iex", l):
        return "remote-script", "CRITICAL", "script piped from the old namespace"
    if re.search(r"\bgit clone\b|pip install git\+|npx .*github:|degit ", l):
        return "copy-paste install", "HIGH", "readers paste this and run whatever the URL serves"
    if name in {"package.json", "setup.py", "pyproject.toml", "setup.cfg"}:
        return "package metadata", "MEDIUM", "published to the registry as the project's repository/homepage"
    if name in {"docs.json", "mint.json"} or "nav" in name or "footer" in l:
        return "site navigation", "HIGH", "a navigation link on a live site"
    return "link", "LOW", "plain link or badge"


def _walk(root):
    for f in Path(root).rglob("*"):
        if f.is_file() and not (SKIP_DIRS & set(f.relative_to(root).parts)) and f.suffix.lower() in TEXT_EXT \
                and f.stat().st_size < 2_000_000:
            yield f


def scan_tree(root, source, old):
    pat, refs = ref_pattern(old), []
    for f in _walk(root):
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for m in pat.finditer(line):
                repo = next((g for g in m.groups() if g), None)
                rel = f.relative_to(root).as_posix()
                kind, sev, why = classify(rel, line)
                refs.append(Ref(source, f"{rel}:{i}", m.group(0), repo, line.strip()[:200], kind, sev, why))
    return refs


def clone_org(org, dest, gh="gh"):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out = subprocess.run([gh, "api", f"orgs/{org}/repos?per_page=100", "--paginate", "-q",
                          ".[] | select(.fork==false) | .name"], capture_output=True, text=True, check=True)
    names = out.stdout.split()
    for n in names:
        if not (dest / n).exists():
            subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{org}/{n}.git", str(dest / n)],
                           check=False)
    return names


def _get_json(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "repojack-scan"}), timeout=20) as r:
            return json.load(r)
    except (urllib.error.URLError, ValueError, TimeoutError):
        return None


def scan_registries(old, npm=(), pypi=()):
    refs = []
    pat = ref_pattern(old)
    for p in npm:
        d = _get_json(f"https://registry.npmjs.org/{p}") or {}
        v = d.get("dist-tags", {}).get("latest")
        meta = d.get("versions", {}).get(v, {}) if v else {}
        dl = (_get_json(f"https://api.npmjs.org/downloads/point/last-month/{p}") or {}).get("downloads", 0)
        fields = {"repository": (meta.get("repository") or {}).get("url", "") if isinstance(meta.get("repository"), dict)
                  else meta.get("repository") or "", "homepage": meta.get("homepage") or "",
                  "bugs": (meta.get("bugs") or {}).get("url", "") if isinstance(meta.get("bugs"), dict) else ""}
        for k, val in fields.items():
            for m in pat.finditer(val or ""):
                repo = next((g for g in m.groups() if g), None)
                refs.append(Ref(f"npm:{p}@{v}", k, m.group(0), repo, val, "registry metadata", "MEDIUM",
                                "the package page links here; fixing needs a new release", weight=dl))
    for p in pypi:
        info = (_get_json(f"https://pypi.org/pypi/{p}/json") or {}).get("info") or {}
        dl = ((_get_json(f"https://pypistats.org/api/packages/{p}/recent") or {}).get("data") or {}).get("last_month", 0)
        fields = {"home_page": info.get("home_page") or "", **{f"project_urls.{k}": u for k, u in (info.get("project_urls") or {}).items()}}
        for k, val in fields.items():
            for m in pat.finditer(val or ""):
                repo = next((g for g in m.groups() if g), None)
                refs.append(Ref(f"pypi:{p}=={info.get('version')}", k, m.group(0), repo, val, "registry metadata",
                                "MEDIUM", "the package page links here; fixing needs a new release", weight=dl))
    return refs


def scan_hf(author, old, kinds=("models", "datasets", "spaces")):
    """README and requirements of every public Hugging Face repo of `author`."""
    refs = []
    pat = ref_pattern(old)
    for kind in kinds:
        for item in _get_json(f"https://huggingface.co/api/{kind}?author={author}&limit=200") or []:
            rid = item["id"]
            prefix = "" if kind == "models" else f"{kind}/"
            for fname in ("README.md", "requirements.txt", "app.py"):
                try:
                    with urllib.request.urlopen(f"https://huggingface.co/{prefix}{rid}/raw/main/{fname}", timeout=20) as r:
                        text = r.read().decode("utf-8", "ignore")
                except (urllib.error.URLError, TimeoutError):
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    for m in pat.finditer(line):
                        repo = next((g for g in m.groups() if g), None)
                        kd, sev, why = classify(fname, line)
                        refs.append(Ref(f"hf:{prefix}{rid}", f"{fname}:{i}", m.group(0), repo, line.strip()[:200], kd, sev, why))
    return refs


def to_json(refs):
    return [asdict(r) for r in refs]
