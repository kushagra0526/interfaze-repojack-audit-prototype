"""findings (+ quickstart issues) → a one-page HTML report."""
import html
from collections import Counter

COL = {"CRITICAL": "#f87171", "HIGH": "#fb923c", "MEDIUM": "#fbbf24", "LOW": "#9aa3b2"}


def render(data, quick=(), title="Old-namespace audit"):
    e = html.escape
    refs = data["refs"]
    by = Counter(r["severity"] for r in refs)
    st = Counter(("REDIRECT" if r["status"].startswith("REDIRECT") else r["status"]) for r in refs)
    owner = data.get("old_owner_now") or {}
    weights = {}
    for r in refs:
        if r["weight"]:
            weights[r["source"]] = r["weight"]
    rows = "".join(
        f"<tr><td><b style='color:{COL[r['severity']]}'>{r['severity']}</b></td><td>{e(r['kind'])}</td>"
        f"<td>{e(r['source'])}</td><td class='mono'>{e(r['location'])}</td><td class='mono'>{e(r['context'][:90])}</td>"
        f"<td>{e(r['status'])}</td></tr>" for r in refs if r["severity"] in ("CRITICAL", "HIGH"))
    rest = Counter((r["severity"], r["kind"]) for r in refs if r["severity"] not in ("CRITICAL", "HIGH"))
    rest_rows = "".join(f"<tr><td><b style='color:{COL[s]}'>{s}</b></td><td>{e(k)}</td><td>{n}</td></tr>"
                        for (s, k), n in sorted(rest.items(), key=lambda x: (x[0][0], -x[1])))
    reg = "".join(f"<li>{e(s)}: <b>{w:,}</b> downloads last month</li>" for s, w in
                  sorted(weights.items(), key=lambda x: -x[1]))
    qrows = "".join(f"<tr><td>{e(q['repo'])}</td><td><b>{e(q['code'])}</b></td><td class='mono'>{e(q['text'])}</td>"
                    f"<td>{e(q['detail'])}</td></tr>" for q in quick)
    owner_html = ""
    if owner.get("exists"):
        owner_html = (f"<div class='warn'><b>github.com/{e(owner['login'])}</b> today: {e(owner['type'])} "
                      f"named “{e(owner.get('name') or '')}”, created {e(owner['created_at'][:10])}, "
                      f"{owner['public_repos']} public repos. Bio: “{e(owner.get('bio') or '')}”</div>")
    cards = "".join(f"<div class='k'><b style='color:{COL[s]}'>{by.get(s, 0)}</b>{s.lower()}</div>"
                    for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW"))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(title)}</title><style>
:root{{--bg:#0f1115;--card:#171a21;--ink:#e8eaf0;--mute:#9aa3b2;--line:#2a2f3a}}
body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,Segoe UI,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:26px 16px}} h1{{font-size:24px;margin:0 0 4px}} h2{{font-size:16px;margin:0 0 8px}}
.sub{{color:var(--mute);margin-bottom:14px}} section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:12px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} td,th{{border-bottom:1px solid var(--line);padding:4px 7px;text-align:left;vertical-align:top}} th{{color:var(--mute);font-weight:500}}
.mono{{font-family:Consolas,monospace;font-size:12px}} .kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:12px}}
.k{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;color:var(--mute)}} .k b{{display:block;font-size:26px}}
.warn{{border:1px solid #7f1d1d;background:#2a1215;border-radius:10px;padding:10px 12px;margin-bottom:12px}}
@media(max-width:800px){{.kpis{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<h1>{e(title)}: {e(data['old'])} → {e(data['org'])}</h1>
<div class="sub">{data['repos_scanned']} repos + package registries + Hugging Face + live site, scanned read-only. Status = what each URL resolves to today.</div>
{owner_html}
<div class="kpis">{cards}<div class="k"><b>{st.get('REDIRECT', 0)}</b>still redirecting</div><div class="k"><b>{st.get('HIJACKED', 0) + st.get('DANGLING', 0)}</b>hijacked / dangling</div></div>
<section><h2>Critical and high</h2><table><tr><th>severity</th><th>kind</th><th>where</th><th>location</th><th>line</th><th>today</th></tr>{rows}</table></section>
<section><h2>The rest</h2><table><tr><th>severity</th><th>kind</th><th>count</th></tr>{rest_rows}</table>
<ul>{reg}</ul></section>
{f"<section><h2>Quickstarts that fail on a fresh clone</h2><table><tr><th>repo</th><th>issue</th><th>line</th><th>why</th></tr>{qrows}</table></section>" if quick else ""}
</main></body></html>"""
