"""Rewrite old-namespace URLs to where GitHub actually redirects them today.

The target comes from the live redirect, not a guess, so renamed repos land correctly
(e.g. old `nextjs-template` -> `InterfazeAI/jigsawstack-starterkit`), and the `cd` after a
`git clone` follows. URLs with no redirect (hijacked or dangling) are left alone for a person
to decide. Only files with references are touched; the rest of each line is preserved.
"""
import re
from pathlib import Path

from .scan import ref_pattern


def rewrite_line(line, old, new, mapping):
    """mapping: {old_repo_lower: 'NewOwner/new-repo'} from resolve()."""
    pat = ref_pattern(old)

    def sub(m):
        s = m.group(0)
        repo = next((g for g in m.groups() if g), None)
        if repo:
            bare = repo[:-4] if repo.lower().endswith(".git") else repo
            suffix = repo[len(bare):]
            target = mapping.get(bare.lower())
            if target is None:          # hijacked or dangling: no known home, a person decides
                return s
            if s.lower().startswith("github:"):
                return f"github:{target}{suffix}"
            if s.lower().startswith("uses:"):
                return re.sub(rf"(?i){re.escape(old)}/{re.escape(repo)}", target + suffix, s)
            return re.sub(rf"(?i){re.escape(old)}/{re.escape(repo)}", target + suffix, s)
        return re.sub(rf"(?i)(github\.com[/:]){re.escape(old)}", rf"\g<1>{new}", s)

    return pat.sub(sub, line)


def _clone_dir(line):
    m = re.search(r"git clone\s+\S*?/([A-Za-z0-9_.-]+?)(?:\.git)?\s*$", line.strip())
    return m.group(1) if m else None


def mapping_from(refs):
    out = {}
    for r in refs:
        if r.repo and r.status.startswith("REDIRECT -> "):
            bare = r.repo[:-4] if r.repo.lower().endswith(".git") else r.repo
            out[bare.lower()] = r.status.split("-> ", 1)[1]
    return out


def apply(root, refs, old, new, only_source=None):
    """Patch files in a cloned repo. Returns {file: n_lines_changed}."""
    mapping = mapping_from(refs)
    changed = {}
    files = {r.location.rsplit(":", 1)[0] for r in refs if only_source is None or r.source == only_source}
    for rel in sorted(files):
        p = Path(root) / rel
        if not p.exists():
            continue
        raw = p.read_bytes()
        text = raw.decode("utf-8")
        nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(nl)
        n = 0
        for i, line in enumerate(lines):
            new_line = rewrite_line(line, old, new, mapping)
            if new_line != line:
                lines[i] = new_line
                n += 1
                a, b = _clone_dir(line), _clone_dir(new_line)
                if a and b and a != b:                       # repo was renamed: the folder name changes too
                    for j in range(i + 1, min(i + 4, len(lines))):
                        m = re.match(rf"^(\s*\$?\s*cd\s+){re.escape(a)}(/?\s*)$", lines[j])
                        if m:
                            lines[j] = f"{m.group(1)}{b}{m.group(2)}"
                            n += 1
                            break
        if n:
            p.write_bytes(nl.join(lines).encode("utf-8"))
            changed[rel] = n
    return changed
