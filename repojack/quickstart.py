"""Lint copy-paste quickstarts in READMEs: do the commands work on a fresh clone of *this* repo?

    CLONE_CD_MISMATCH   `git clone .../X` followed by `cd Y` where Y is not the folder git creates
    WRONG_REPO          the README clones a different repository than the one it lives in
    MISSING_FILE        `cp A B`, `source A`, `cat A`... where A is not in the repository
    IGNORED_EXAMPLE     the missing file is matched by .gitignore (e.g. `.env*` swallows `.env.example`)
"""
import fnmatch
import re
import subprocess
from pathlib import Path

CLONE = re.compile(r"git clone\s+(?:--[\w-]+(?:\s+\S+)?\s+)*(\S+?)(?:\.git)?(?:\s+(\S+))?\s*$")
CD = re.compile(r"^\s*\$?\s*cd\s+([^\s&;]+)")
USES_FILE = re.compile(r"^\s*\$?\s*(?:cp|source|cat|mv)\s+([./\w-]+\.[\w.-]+|\.[\w.-]+)")


def _code_blocks(text):
    """(start_line, [lines]) for each fenced shell-ish block."""
    out, cur, start = [], None, 0
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            if cur is None:
                cur, start = [], i + 1
            else:
                out.append((start, cur))
                cur = None
        elif cur is not None:
            cur.append(line)
    return out


def _tracked(root):
    r = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True)
    return set(r.stdout.split()) if r.returncode == 0 else {p.relative_to(root).as_posix()
                                                             for p in Path(root).rglob("*") if p.is_file()}


def _ignored_by(root, name):
    gi = Path(root) / ".gitignore"
    if not gi.exists():
        return None
    for pat in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
        p = pat.strip()
        if p and not p.startswith(("#", "!")) and fnmatch.fnmatch(name, p.lstrip("/")):
            return p
    return None


def lint(root, repo_name, readme="README.md"):
    root = Path(root)
    f = root / readme
    if not f.exists():
        return []
    tracked = _tracked(root)
    issues = []
    for start, block in _code_blocks(f.read_text(encoding="utf-8", errors="ignore")):
        cwd = None
        for k, line in enumerate(block):
            ln = start + k
            m = CLONE.search(line.strip().lstrip("$ ").strip())
            if m:
                url, folder = m.group(1), m.group(2)
                cloned = url.rstrip("/").split("/")[-1]
                cwd = folder or cloned
                if cloned.lower() != repo_name.lower():
                    issues.append({"code": "WRONG_REPO", "line": ln, "text": line.strip(),
                                   "detail": f"clones '{cloned}' but this README belongs to '{repo_name}'"})
                for j in range(k + 1, min(k + 4, len(block))):
                    c = CD.match(block[j].lstrip("$ "))
                    if c:
                        if c.group(1).rstrip("/") != cwd:
                            issues.append({"code": "CLONE_CD_MISMATCH", "line": start + j, "text": block[j].strip(),
                                           "detail": f"git creates '{cwd}', the next step cds into '{c.group(1)}'"})
                        break
                continue
            u = USES_FILE.match(line)
            if u and cwd is not None:
                name = re.sub(r"^\./", "", u.group(1))
                if name not in tracked and not any(t.endswith("/" + name) for t in tracked):
                    pat = _ignored_by(root, name)
                    issues.append({"code": "IGNORED_EXAMPLE" if pat else "MISSING_FILE", "line": ln,
                                   "text": line.strip(),
                                   "detail": f"'{name}' is not in the repo" + (f"; .gitignore '{pat}' matches it" if pat else "")})
    return issues
