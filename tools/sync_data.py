#!/usr/bin/env python3
"""Sync project data from the NUSV GitHub organization into static pages.

Fetches, for each configured project:
  - repository metadata (description, license, stars, updated_at)
  - latest releases + assets
  - README.md (rendered to a safe HTML subset)

Generates:
  projects/<slug>.html   - project page (intro + downloads, Modrinth-like)

Run:  python3 tools/sync_data.py [--token TOKEN]
Scheduled by .github/workflows/sync.yml (every 6h + manual dispatch).
"""

import argparse
import base64
import datetime
import html
import json
import os
import re
import sys
import urllib.request
import urllib.error

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

PROJECTS = [
    {
        "slug": "syna",
        "repo": "Syna-NUSV",
        "branch": "main",
        "name": "Syna",
        "tagline": "Offline-first LAN messenger with end-to-end encryption, group chat, self-hosted servers and a built-in anti-tamper shield.",
        "docs": "../docs/syna.html",
        "icon": "../assets/img/syna-icon.png",
        "banner": "../assets/img/syna-banner.svg",
        "platforms": ["Android", "Windows", "macOS"],
    },
    {
        "slug": "nusv-lite",
        "repo": "NUSV-lite",
        "branch": "test-orca",
        "name": "NUSV LITE",
        "tagline": "The official NUSV Android client: content hub, 11 built-in games, 60+ tools, widgets, theme store and daily check-in points.",
        "docs": "../docs/nusv-lite.html",
        "icon": "../assets/img/lite-icon.png",
        "banner": "../assets/img/lite-banner.svg",
        "platforms": ["Android"],
    },
    {
        "slug": "gomoku",
        "repo": "Gomoku-NUSV",
        "branch": "main",
        "name": "Gomoku-NUSV",
        "tagline": "A polished cross-platform Five-in-a-Row game with on-device AI across three difficulty levels — no network needed.",
        "docs": "../docs/gomoku.html",
        "icon": "../assets/img/gomoku-icon.png",
        "banner": "../assets/img/gomoku-banner.svg",
        "platforms": ["macOS", "Windows", "iOS", "Android"],
    },
]

PLATFORM_BY_EXT = {
    ".apk": ("Android APK", "green"),
    ".dmg": ("macOS (.dmg)", "cyan"),
    ".msi": ("Windows (.msi)", "cyan"),
    ".exe": ("Windows (.exe)", "cyan"),
    ".deb": ("Linux (.deb)", "cyan"),
    ".jar": ("Server / other (.jar)", "muted"),
    ".ipa": ("iOS (.ipa)", "muted"),
}


def http_json(url, token):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "nusv-site-sync")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def http_text(url, token):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "nusv-site-sync")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def fetch_meta(proj, token):
    return http_json("%s/repos/NUSV/%s" % (API, proj["repo"]), token)


def fetch_releases(proj, token):
    data = http_json(
        "%s/repos/NUSV/%s/releases?per_page=8" % (API, proj["repo"]), token
    )
    out = []
    for rel in data or []:
        out.append(
            {
                "tag": rel.get("tag_name", ""),
                "name": rel.get("name") or rel.get("tag_name", ""),
                "published": rel.get("published_at", ""),
                "html_url": rel.get("html_url", ""),
                "assets": [
                    {
                        "name": a.get("name", ""),
                        "size": a.get("size", 0),
                        "url": a.get("browser_download_url", ""),
                    }
                    for a in rel.get("assets", [])
                ],
            }
        )
    return out


def fetch_readme(proj, token):
    url = "%s/NUSV/%s/%s/README.md" % (RAW, proj["repo"], proj["branch"])
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "nusv-site-sync")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError:
        return None


def resolve_ref(proj, raw):
    """Resolve a README-relative reference to a GitHub URL."""
    raw = raw.strip()
    if raw.startswith(("http://", "https://", "#", "mailto:", "data:")):
        return raw
    raw = raw.lstrip("./")
    if raw.startswith("http"):
        return raw
    return "%s/NUSV/%s/%s/%s" % (
        "https://github.com",
        proj["repo"],
        proj["branch"],
        raw,
    )


def md_inline(text, proj):
    """Convert inline markdown (code, bold, italic, links, images) to HTML."""
    img_tokens = {}

    def img_placeholder(m):
        alt, src, title = m.group(1), m.group(2), m.group(3)
        key = "IMGTOK%d" % len(img_tokens)
        img_tokens[key] = (
            '<img src="%s" alt="%s" loading="lazy" referrerpolicy="no-referrer">'
            % (html.escape(resolve_ref(proj, src), quote=True),
               html.escape(alt or "", quote=True))
        )
        return key

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^)]*)&quot;)?\)", img_placeholder, text)

    text = re.sub(r"`([^`]+)`", lambda m: "<code>%s</code>" % html.escape(m.group(1)), text)
    text = re.sub(r"\*\*([^*]+)\*\*", lambda m: "<strong>%s</strong>" % m.group(1), text)
    text = re.sub(r"__([^_]+)__", lambda m: "<strong>%s</strong>" % m.group(1), text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", lambda m: "<em>%s</em>" % m.group(1), text)

    def link(m):
        lab, dst = m.group(1), m.group(2)
        target = ' target="_blank" rel="noopener"' if dst.startswith("http") else ""
        return '<a href="%s"%s>%s</a>' % (
            html.escape(resolve_ref(proj, dst), quote=True),
            target,
            lab,
        )

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^)]*&quot;)?\)", link, text)

    for key, val in img_tokens.items():
        text = text.replace(key, val)
    return text


def md_to_html(md, proj):
    """Render a pragmatic README subset to HTML (headings, lists, code, tables,
    blockquotes, hr, paragraphs). Everything else is escaped text."""
    out = []
    lines = md.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)

    def flush():
        pass

    while i < n:
        line = lines[i]

        if line.startswith("```"):
            fence = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                fence.append(lines[i])
                i += 1
            i += 1
            out.append("<pre class=\"doc-code\">%s</pre>" % html.escape("\n".join(fence)))
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            lvl = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (lvl, md_inline(m.group(2), proj), lvl))
            i += 1
            continue

        if re.match(r"^\s*(---+|\*\*\*+)\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        if line.strip().startswith(("> ", ">")):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i], count=1))
                i += 1
            inner = md_to_html("\n".join(quote), proj)
            out.append("<blockquote>%s</blockquote>" % inner)
            continue

        if re.match(r"^\s*[-*+]\s+", line) or re.match(r"^\s*\d+[.)]\s+", line):
            items = []
            ordered = bool(re.match(r"^\s*\d+[.)]\s+", line))
            while i < n:
                m2 = re.match(r"^\s*[-*+]\s+(.*)$", lines[i])
                m3 = re.match(r"^\s*\d+[.)]\s+(.*)$", lines[i])
                if ordered and m3:
                    items.append(m3.group(1))
                elif not ordered and m2:
                    items.append(m2.group(1))
                elif lines[i].strip() == "":
                    i += 1
                    continue
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(
                "<%s>%s</%s>"
                % (
                    tag,
                    "".join("<li>%s</li>" % md_inline(it, proj) for it in items),
                    tag,
                )
            )
            continue

        if line.startswith("|"):
            rows = []
            while i < n and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            if len(rows) >= 2:
                head = [c.strip() for c in rows[0].strip("|").split("|")]
                body = rows[2:]
                tbl = ["<table><thead><tr>"]
                tbl.extend("<th>%s</th>" % md_inline(c, proj) for c in head)
                tbl.append("</tr></thead><tbody>")
                for r in body:
                    cells = [c.strip() for c in r.strip("|").split("|")]
                    tbl.append("<tr>")
                    tbl.extend("<td>%s</td>" % md_inline(c, proj) for c in cells)
                    tbl.append("</tr>")
                tbl.append("</tbody></table>")
                out.append("".join(tbl))
                continue
            out.append(md_inline(line, proj))
            i += 1
            continue

        if line.strip() == "":
            i += 1
            continue

        para = []
        while i < n and lines[i].strip() != "" and not lines[i].startswith(("#", "```", "|", "> ")):
            if re.match(r"^\s*[-*+]\s+", lines[i]) or re.match(r"^\s*\d+[.)]\s+", lines[i]):
                break
            para.append(lines[i])
            i += 1
        out.append("<p>%s</p>" % md_inline(" ".join(x.strip() for x in para), proj))

    return "\n".join(out)


def human_size(num):
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return "%.0f %s" % (num, unit) if unit == "B" else "%.1f %s" % (num, unit)
        num /= 1024.0
    return str(num)


def fmt_iso(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return (iso or "")[:10]


NAV = """  <header class="nav">
    <div class="wrap nav-inner">
      <a class="brand" href="../index.html">
        <span class="brand-mark"><img src="../assets/img/nusv-logo.png" alt="NUSV" loading="lazy"></span>
        NUSV <small>United Science Vaca</small>
      </a>
      <nav class="nav-links">
        <a href="../index.html">Home</a>
        <a href="../warehouse.html">Warehouse</a>
        <a href="../docs.html">Docs</a>
        <a href="../about.html">About</a>
      </nav>
      <span class="nav-cta">
        <button class="lang-toggle" id="lang-toggle" data-lang="en" title="中文版即将推出">EN</button>
      </span>
    </div>
  </header>"""

FOOTER = """  <footer class="footer">
    <div class="wrap footer-inner">
      <span>&copy; <span class="year"></span> United Science Vaca (NUSV). Open source.</span>
      <span><a href="https://github.com/NUSV" target="_blank" rel="noopener">GitHub</a> &middot; <a href="../warehouse.html">Warehouse</a> &middot; <a href="../docs.html">Docs</a></span>
    </div>
  </footer>"""


def render_page(proj, meta, releases, readme_html, updated_utc):
    repo_url = meta["html_url"] if meta else "https://github.com/NUSV/" + proj["repo"]
    license_txt = ((meta or {}).get("license") or {}).get("spdx_id") or "—"
    stars = (meta or {}).get("stargazers_count", 0)
    topics = ((meta or {}).get("topics") or [])[:5]
    updated_repo = ((meta or {}).get("pushed_at") or "")[:10]

    chips = ["".join('<span class="chip chip-accent">%s</span>' % p for p in proj["platforms"])]
    chips.append('<span class="chip">%s</span>' % license_txt)
    for t in topics:
        chips.append('<span class="chip">%s</span>' % html.escape(t))

    latest = releases[0] if releases else None

    def dl_row(asset, big=False):
        label, kind = PLATFORM_BY_EXT.get(
            os.path.splitext(asset["name"].lower())[1], ("Download", "muted")
        )
        cls = "dl-btn" if not big else "dl-btn big"
        return (
            '<a class="%s %s" href="%s" target="_blank" rel="noopener">'
            '<span class="dl-label">%s</span>'
            '<span class="dl-sub">%s &middot; %s</span></a>'
            % (cls, kind, html.escape(asset["url"], quote=True),
               html.escape(label), html.escape(asset["name"]), human_size(asset["size"]))
        )

    if latest:
        top = latest["assets"][:3] if latest["assets"] else []
        alln = len(latest["assets"])
        dl_latest = "".join(dl_row(a, big=True) for a in top)
        if alln > len(top):
            dl_latest += (
                '<a class="dl-btn muted" href="%s" target="_blank" rel="noopener">'
                '<span class="dl-label">All %d assets</span>'
                '<span class="dl-sub">open the release page</span></a>'
                % (html.escape(latest["html_url"], quote=True), alln)
            )
        head_sub = (
            '<span class="rel-tag">%s</span><span class="rel-date">%s</span>'
            % (html.escape(latest["tag"]), fmt_iso(latest["published"]))
        )
    else:
        dl_latest = ""
        head_sub = '<span class="rel-tag">no releases yet</span>'

    rel_items = []
    for rel in releases[1:]:
        rel_items.append(
            '<a class="rel-item" href="%s" target="_blank" rel="noopener">'
            '<span class="rel-tag">%s</span>'
            '<span class="rel-date">%s</span>'
            '<span class="rel-assets">%d assets</span></a>'
            % (html.escape(rel["html_url"], quote=True), html.escape(rel["tag"]),
               fmt_iso(rel["published"]), len(rel["assets"]))
        )

    sidebar = []
    sidebar.append(
        '<div class="card pg-side">'
        '<div class="side-title">Latest release</div>'
        '%s<div class="dl-group">%s</div></div>'
        % (head_sub, dl_latest)
    )
    if rel_items:
        sidebar.append(
            '<div class="card pg-side"><div class="side-title">Recent versions</div>%s</div>'
            % "".join(rel_items)
        )
    sidebar.append(
        '<div class="card pg-side"><div class="side-title">Project info</div>'
        '<div class="pg-info"><span>License</span><b>%s</b></div>'
        '<div class="pg-info"><span>Stars</span><b>%d</b></div>'
        '<div class="pg-info"><span>Repository updated</span><b>%s</b></div>'
        '<div class="pg-info"><span>Source</span><a href="%s" target="_blank" rel="noopener">github.com/NUSV/%s</a></div>'
        '</div>'
        % (html.escape(license_txt), stars, html.escape(updated_repo),
           html.escape(repo_url, quote=True), proj["repo"])
    )

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>%s — Downloads &amp; Introduction | United Science Vaca (NUSV)</title>
  <meta name="description" content="%s">
  <link rel="icon" type="image/png" href="../assets/img/nusv-logo.png">
  <link rel="stylesheet" href="../assets/css/style.css">
</head>
<body>

%s

  <main class="wrap">
    <article class="pg">

      <div class="pg-head">
        <div class="pg-head-main">
          <span class="pg-icon"><img src="%s" alt="%s icon" loading="lazy"></span>
          <h1>%s</h1>
          <p class="lede">%s</p>
          <div class="meta pg-chips">%s</div>
          <div class="btn-row pg-actions">
            <a class="btn btn-primary" href="#downloads">Download latest</a>
            <a class="btn btn-ghost" href="%s" target="_blank" rel="noopener">GitHub repository</a>
            <a class="btn btn-ghost" href="%s">Technical docs</a>
          </div>
        </div>
      </div>

      <div class="pg-grid">
        <section class="pg-about">
          <div class="pg-updated">README auto-synced from the repository &middot; %s UTC</div>
          %s
        </section>
        <aside class="pg-sidecol" id="downloads">
          %s
        </aside>
      </div>

    </article>
  </main>

%s

  <script src="../assets/js/main.js"></script>
</body>
</html>
""" % (
        html.escape(proj["name"]),
        html.escape(proj["tagline"][:150], quote=True),
        NAV,
        proj["icon"], html.escape(proj["name"]), html.escape(proj["name"]),
        html.escape(proj["tagline"]),
        "".join(chips),
        html.escape(repo_url, quote=True),
        proj["docs"],
        updated_utc,
        readme_html or "<p><em>README not found.</em></p>",
        "".join(sidebar),
        FOOTER,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=None)
    args = ap.parse_args()
    token = args.token or os.environ.get("NUSV_SYNC_TOKEN") or os.environ.get("GITHUB_TOKEN")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outdir = os.path.join(root, "projects")
    os.makedirs(outdir, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")

    changed = []
    for proj in PROJECTS:
        meta = fetch_meta(proj, token)
        releases = fetch_releases(proj, token) or []
        md = fetch_readme(proj, token)
        readme_html = md_to_html(md, proj) if md else None
        page = render_page(proj, meta, releases, readme_html, now)
        path = os.path.join(outdir, proj["slug"] + ".html")
        old = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                old = f.read()
        if old != page:
            with open(path, "w", encoding="utf-8") as f:
                f.write(page)
            changed.append(proj["slug"])
        print("synced %s (%d releases, %s)" % (
            proj["slug"], len(releases), "changed" if proj["slug"] in changed else "unchanged"))

    print("changed: %s" % (", ".join(changed) if changed else "none"))
    sys.exit(0)


if __name__ == "__main__":
    main()
