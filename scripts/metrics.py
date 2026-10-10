"""Render the profile's metrics panel (metrics.svg) from the GitHub GraphQL API.

Usage:
  GITHUB_TOKEN=... python3 scripts/metrics.py dist/metrics.svg
  python3 scripts/metrics.py out.svg --fixture data.json   # render saved data
"""
import base64, datetime as dt, json, os, re, sys, urllib.parse, urllib.request
from xml.sax.saxutils import escape

LOGIN = "crlsyajie"
HIDDEN_LANGS = {"Jupyter Notebook"}  # notebook JSON dwarfs real source code
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

BG, LINE = "#0B0B0C", "#232326"
GOLD, GOLD_DIM = "#C9A86A", "#7A6743"
IVORY, MUTED, FAINT = "#EDE6D6", "#9C9A94", "#5E5C58"
SERIF = "'Cormorant Garamond', Georgia, 'Times New Roman', serif"
MONO = "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace"


# ---------- Data ----------
def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}", "User-Agent": LOGIN},
    )
    body = json.load(urllib.request.urlopen(req))
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


def fetch():
    q = """query($login:String!, $after:String) { user(login:$login) {
      followers { totalCount }
      pullRequests { totalCount }
      contributionsCollection {
        totalCommitContributions
        contributionYears
        contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
      }
      repositories(ownerAffiliations:OWNER, privacy:PUBLIC, first:100, after:$after) {
        pageInfo { hasNextPage endCursor }
        nodes { isFork stargazerCount
          languages(first:20, orderBy:{field:SIZE, direction:DESC}) { edges { size node { name } } } }
      } } }"""
    repos, after = [], None
    while True:
        u = gql(q, {"login": LOGIN, "after": after})["user"]
        repos += u["repositories"]["nodes"]
        if not u["repositories"]["pageInfo"]["hasNextPage"]:
            break
        after = u["repositories"]["pageInfo"]["endCursor"]
    cc = u["contributionsCollection"]

    # Every day ever, so the longest streak covers all years, not just the last 12 months.
    days = {}
    for year in cc["contributionYears"]:
        yq = """query($login:String!, $from:DateTime!, $to:DateTime!) { user(login:$login) {
          contributionsCollection(from:$from, to:$to) { contributionCalendar {
            weeks { contributionDays { date contributionCount } } } } } }"""
        cal = gql(yq, {"login": LOGIN, "from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"})
        for w in cal["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    langs = {}
    for r in repos:
        if r["isFork"]:
            continue
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]

    return {
        "followers": u["followers"]["totalCount"],
        "pull_requests": u["pullRequests"]["totalCount"],
        "commits_year": cc["totalCommitContributions"],
        "contributions_year": cc["contributionCalendar"]["totalContributions"],
        "year_days": [[d["date"], d["contributionCount"]]
                      for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]],
        "all_days": sorted(days.items()),
        "repos_original": sum(1 for r in repos if not r["isFork"]),
        "repos_forked": sum(1 for r in repos if r["isFork"]),
        "stars": sum(r["stargazerCount"] for r in repos),
        "languages": langs,
        "updated": dt.date.today().isoformat(),
    }


# ---------- Derived ----------
def streaks(all_days, today):
    days = [(dt.date.fromisoformat(d), c) for d, c in all_days if dt.date.fromisoformat(d) <= today]
    longest, run, start, best = 0, 0, None, (None, None)
    for d, c in days:
        if c > 0:
            run, start = run + 1, start or d
            if run > longest:
                longest, best = run, (start, d)
        else:
            run, start = 0, None
    # Current streak: today may still be empty without breaking it.
    cur, end = 0, None
    for d, c in reversed(days):
        if c > 0:
            cur, end = cur + 1, end or d
        elif d != today or cur:
            break
    cur_start = end - dt.timedelta(days=cur - 1) if cur else None
    return cur, cur_start, longest, best


def fmt(d):
    return f"{d.strftime('%b')} {d.day}" if d else "—"


# ---------- SVG ----------
def t(x, y, s, size, fill, family=MONO, weight=400, anchor="start", ls=0, extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" font-weight="{weight}" fill="{fill}"'
            f' text-anchor="{anchor}" letter-spacing="{ls}" xml:space="preserve"'
            f' style="font-variant-numeric: lining-nums tabular-nums" {extra}>{escape(str(s))}</text>')


def render(m):
    today = dt.date.fromisoformat(m["updated"])
    cur, cur_start, longest, (l_start, l_end) = streaks(m["all_days"], today)
    W, X0, X1 = 1200, 48, 1152
    b = []

    # Section head
    b.append(t(X0, 58, "06", 13, GOLD, weight=500, ls=2))
    b.append(f'<line x1="{X0+34}" y1="54" x2="{X0+74}" y2="54" stroke="{GOLD_DIM}"/>')
    b.append(t(X0 + 88, 58, "METRICS", 13, MUTED, weight=500, ls=4))
    b.append(t(X1, 58, f"UPDATED {today.day} {today.strftime('%b %Y').upper()}", 11, FAINT, anchor="end", ls=3))
    b.append(f'<line x1="{X0}" y1="80" x2="{X1}" y2="80" stroke="{LINE}"/>')

    # KPI tiles
    tiles = [
        ("CONTRIBUTIONS", m["contributions_year"], "LAST 12 MONTHS"),
        ("CURRENT STREAK", cur, f"DAYS · SINCE {fmt(cur_start).upper()}" if cur else "DAYS"),
        ("LONGEST STREAK", longest, f"DAYS · {fmt(l_start).upper()} – {fmt(l_end).upper()}"),
        ("COMMITS", m["commits_year"], "LAST 12 MONTHS"),
        ("PULL REQUESTS", m["pull_requests"], "ALL TIME"),
        ("REPOSITORIES", m["repos_original"], f"ORIGINAL · {m['repos_forked']} FORKED"),
        ("STARS EARNED", m["stars"], "ACROSS PUBLIC REPOS"),
        ("FOLLOWERS", m["followers"], "ON GITHUB"),
    ]
    tw, th, gap = (X1 - X0 - 3 * 16) / 4, 116, 16
    for i, (label, val, sub) in enumerate(tiles):
        x, y = X0 + (i % 4) * (tw + gap), 104 + (i // 4) * (th + gap)
        b.append(f'<rect x="{x:.1f}" y="{y}" width="{tw:.1f}" height="{th}" rx="6" fill="#0F0F11" stroke="{LINE}"/>')
        b.append(t(x + 22, y + 32, label, 11, GOLD, weight=500, ls=3))
        b.append(t(x + 22, y + 82, f"{val:,}", 48, IVORY, SERIF, 500))
        b.append(t(x + 22, y + 102, sub, 10, FAINT, ls=1.5))

    # Weekly activity, last 52 weeks
    y0 = 400
    b.append(t(X0, y0, "ACTIVITY", 11, GOLD, weight=500, ls=3))
    b.append(t(X0 + 104, y0, "CONTRIBUTIONS PER WEEK · LAST 52 WEEKS", 11, FAINT, ls=2))
    days = [(dt.date.fromisoformat(d), c) for d, c in m["year_days"]]
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)][-52:]
    totals = [sum(c for _, c in w) for w in weeks]
    top = max(totals) or 1
    base, hmax, bgap = y0 + 160, 120, 4
    bw = (X1 - X0 - (len(weeks) - 1) * bgap) / len(weeks)
    b.append(f'<line x1="{X0}" y1="{base}" x2="{X1}" y2="{base}" stroke="{LINE}"/>')
    peak = totals.index(top)
    last_month = None
    for i, (w, total) in enumerate(zip(weeks, totals)):
        x = X0 + i * (bw + bgap)
        h = max(2, total / top * hmax) if total else 2
        fill = GOLD if total else "#1C1C1F"
        b.append(f'<path d="M{x:.1f} {base} V{base-h+3:.1f} Q{x:.1f} {base-h:.1f} {x+3:.1f} {base-h:.1f} H{x+bw-3:.1f}'
                 f' Q{x+bw:.1f} {base-h:.1f} {x+bw:.1f} {base-h+3:.1f} V{base} Z" fill="{fill}"'
                 f' fill-opacity="{1 if i == peak else 0.75 if total else 1}"/>')
        month = w[0][0].month
        if month != last_month and i < len(weeks) - 2:
            b.append(t(x, base + 22, w[0][0].strftime("%b").upper(), 10, FAINT, ls=1.5))
            last_month = month
    px = X0 + peak * (bw + bgap) + bw / 2
    b.append(t(px, base - top / top * hmax - 10, f"{top}", 12, IVORY, weight=500, anchor="middle"))

    # Languages (ranked bars) and weekday rhythm
    y1 = base + 70
    b.append(f'<line x1="{X0}" y1="{y1-30}" x2="{X1}" y2="{y1-30}" stroke="{LINE}"/>')
    langs = sorted(((k, v) for k, v in m["languages"].items() if k not in HIDDEN_LANGS), key=lambda kv: -kv[1])
    total = sum(v for _, v in langs) or 1
    shown = langs[:6]
    b.append(t(X0, y1, "LANGUAGES", 11, GOLD, weight=500, ls=3))
    b.append(t(X0 + 116, y1, "BY CODE SIZE · ORIGINAL REPOS", 11, FAINT, ls=2))
    lx, lw = X0 + 130, 360
    for i, (name, v) in enumerate(shown):
        y = y1 + 40 + i * 32
        pct = v / total * 100
        b.append(t(X0, y + 4, name, 13, IVORY))
        b.append(f'<rect x="{lx}" y="{y-6}" width="{lw}" height="8" rx="4" fill="#1C1C1F"/>')
        b.append(f'<rect x="{lx}" y="{y-6}" width="{max(8, pct/100*lw):.1f}" height="8" rx="4" fill="{GOLD}"/>')
        b.append(t(lx + lw + 16, y + 4, f"{pct:.1f}%", 12, MUTED, anchor="start"))

    rx0 = 660
    b.append(f'<line x1="{rx0-36}" y1="{y1-10}" x2="{rx0-36}" y2="{y1 + 40 + 5*32 + 10}" stroke="{LINE}"/>')
    b.append(t(rx0, y1, "RHYTHM", 11, GOLD, weight=500, ls=3))
    b.append(t(rx0 + 90, y1, "CONTRIBUTIONS BY WEEKDAY", 11, FAINT, ls=2))
    by_day = [0] * 7
    for d, c in days:
        by_day[d.weekday()] += c
    names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    dtop = max(by_day) or 1
    cw, cg, cbase, ch = 52, 18, y1 + 40 + 5 * 32 - 14, 150
    for i, c in enumerate(by_day):
        x = rx0 + i * (cw + cg)
        h = max(2, c / dtop * ch)
        b.append(f'<rect x="{x}" y="{cbase-h:.1f}" width="{cw}" height="{h:.1f}" rx="3"'
                 f' fill="{GOLD}" fill-opacity="{1 if c == dtop else 0.55}"/>')
        b.append(t(x + cw / 2, cbase + 22, names[i], 10, IVORY if c == dtop else FAINT, anchor="middle", ls=1.5))
        b.append(t(x + cw / 2, cbase - h - 8, f"{c}", 11, MUTED if c != dtop else IVORY, anchor="middle"))
    best = names[by_day.index(dtop)]
    H = cbase + 96
    b.append(f'<line x1="{X0}" y1="{H-50}" x2="{X1}" y2="{H-50}" stroke="{LINE}"/>')
    b.append(t(X0, H - 22, f"MOST ACTIVE ON {dict(zip(names, ['MONDAYS','TUESDAYS','WEDNESDAYS','THURSDAYS','FRIDAYS','SATURDAYS','SUNDAYS']))[best]}", 10, FAINT, ls=2.5))
    b.append(t(X1, H - 22, "REFRESHED TWICE DAILY BY GITHUB ACTIONS", 10, FAINT, anchor="end", ls=2.5))

    body = f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" fill="{BG}" stroke="{LINE}"/>' + "".join(b)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H:.0f}" viewBox="0 0 {W} {H:.0f}" role="img"'
            f' aria-label="GitHub metrics for {LOGIN}"><style>{fonts(body)}</style>{body}</svg>')


def fonts(body):
    """Embed Cormorant Garamond and JetBrains Mono, subset to the glyphs used."""
    txt = re.sub(r"<[^>]+>", " ", body).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    url = ("https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500&family=JetBrains+Mono:wght@400;500&text="
           + urllib.parse.quote("".join(sorted(set(txt)))))
    get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA})).read()
    css = get(url).decode()
    css = re.sub(r"url\((https://[^)]+)\)", lambda m: "url(data:font/woff2;base64," + base64.b64encode(get(m.group(1))).decode() + ")", css)
    return re.sub(r"\s*unicode-range:[^;]+;", "", css)


if __name__ == "__main__":
    out = sys.argv[1]
    data = json.load(open(sys.argv[3])) if "--fixture" in sys.argv else fetch()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        f.write(render(data))
    print(f"wrote {out}")
