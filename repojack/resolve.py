"""What does each old URL point at *today*? And who owns the old name?

    REDIRECT -> owner/repo   GitHub still forwards it (safe until someone creates that repo name)
    HIJACKED                 a different owner now serves a real repository at that URL
    DANGLING                 404: anyone holding the old name can create it right now, no redirect to beat
    PROFILE_CLAIMED          the bare profile URL: shows the new owner of the name today
"""
import http.client
import json
import subprocess
from urllib.parse import urlparse


def _head(path):
    c = http.client.HTTPSConnection("github.com", timeout=20)
    c.request("HEAD", path, headers={"User-Agent": "repojack-scan"})
    r = c.getresponse()
    return r.status, r.getheader("Location") or ""


def owner_info(name, gh="gh"):
    out = subprocess.run([gh, "api", f"users/{name}"], capture_output=True, text=True)
    if out.returncode:
        return {"exists": False}
    d = json.loads(out.stdout)
    return {"exists": True, "login": d["login"], "type": d["type"], "name": d.get("name"),
            "created_at": d["created_at"], "public_repos": d["public_repos"], "bio": d.get("bio")}


def resolve(refs, old, new, head=_head, cache=None):
    cache = {} if cache is None else cache
    for r in refs:
        if not r.repo:
            r.status = "PROFILE_CLAIMED"
            r.fix_to = f"https://github.com/{new}"
            if r.severity == "LOW":
                r.severity, r.why = "HIGH", "the old profile now belongs to someone else; this link lands there today"
            continue
        repo = r.repo[:-4] if r.repo.lower().endswith(".git") else r.repo
        if repo not in cache:
            status, loc = head(f"/{old}/{repo}")
            cache[repo] = (status, loc)
        status, loc = cache[repo]
        if status in (301, 302) and loc:
            parts = urlparse(loc).path.strip("/").split("/")
            target = "/".join(parts[:2])
            r.status = f"REDIRECT -> {target}"
            r.fix_to = f"https://github.com/{target}"
        elif status == 200:
            r.status = "HIJACKED"
            r.severity = "CRITICAL"
            r.why = "a repository with this name already exists under the new owner of the old namespace"
        else:
            r.status = "DANGLING"
            if r.severity in ("LOW", "MEDIUM"):
                r.severity = "HIGH"
            r.why = "no redirect: the new owner of the name can create this repo now"
    return refs
