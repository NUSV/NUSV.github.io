#!/usr/bin/env python3
"""Auto-discover NUSV projects and generate the website's project pages.

Discovery rule (self-service, no hardcoding):
  A repository in the NUSV organization is treated as a project when it has
  the GitHub topic "nusv-project". Infrastructure repos (.github,
  NUSV.github.io, nusv-lite-sync, ...) simply never carry that topic.

Per-project conventions (all optional):
  site.json in the repo root:
    {
      "name": "Syna",                       # display name (default: repo name, minus a trailing "-NUSV")
      "tagline": "one-liner",               # default: repository description
      "platforms": ["Android", "Windows"],  # default: []
      "docs": "/docs/syna.html",            # site-relative (leading /) or absolute URL
      "icon": "logo.png"                    # path in the repo, default: auto-discovered
    }
  Icon auto-discovery: any *.png in the repo root named like the repo,
  "logo*" or "icon*"; the last one alphabetically wins (Syna_logo_2.png
  beats Syna_logo.png).
  Screenshots: images under screenshots/ | docs/screenshots/ |
  assets/screenshots/ are rendered as a gallery on the project page.

Generated outputs:
  projects/<slug>.html  - one page per discovered project
  index.html            - the "Featured projects" grid (kept in sync via markers)
  warehouse.html        - the "Everything we ship" grid (kept in sync via markers)

Run: python3 tools/sync_data.py [--token TOKEN]
Scheduled by .github/workflows/sync.yml (every 6h + manual dispatch).
"""

import argparse
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
ORG = "NUSV"
PROJECT_TOPIC = "nusv-project"
REPOS_PER_PAGE = 100

# Output files the generator rewrites between markers.
INDEX_FEATURED = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html"
)
WAREHOUSE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "warehouse.html"
)

FEAT_START = "<!-- FEATURED-GRID:start -->"
FEAT_END = "<!-- FEATURED-GRID:end -->"
WH_START = "<!-- WAREHOUSE-GRID:start -->"
WH_END = "<!-- WAREHOUSE-GRID:end -->"

# Icon names to look for in the repo root (lower-cased, prefix match).
ICON_PREFIXES = ("logo", "icon")

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


class HttpError(Exception):
    pass


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
        if e.code in (404,):
            return None
        raise HttpError("%s -> %s" % (url, e))


def http_text(url, token):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "nusv-site-sync")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            return None
        raise HttpError("%s -> %s" % (url, e))


# --------------------------------------------------------------------------
# GitHub data
# --------------------------------------------------------------------------

def list_org_repos(token):
    out, page = [], 1
    while True:
        batch = http_json(
            "%s/orgs/%s/repos?per_page=%d&page=%d&type=public"
            % (API, ORG, REPOS_PER_PAGE, page),
            token,
        )
        if not batch:
            break
        out.extend(batch)
        if len(batch) < REPOS_PER_PAGE:
            break
        page += 1
    return out


def get_topics(repo_name, token):
    data = http_json(
        "%s/repos/%s/%s/topics" % (API, ORG, repo_name),
        token,
    )
    if not data:
        return []
    # The list endpoint can be served without the topics accept header value;
    # topics arrive under .names.
    return data.get("names", [])


def get_site_json(repo_name, branch, token):
    data = http_json(
        "%s/repos/%s/%s/contents/site.json?ref=%s" % (API, ORG, repo_name, branch),
        token,
    )
    if not data or not data.get("content"):
        return {}
    try:
        return json.loads(__import__("base64").b64decode(data["content"]).decode("utf-8"))
    except Exception:
        return {}


def get_root_files(repo_name, branch, token):
    data = http_json(
        "%s/repos/%s/%s/contents?ref=%s" % (API, ORG, repo_name, branch), token
    )
    return [f["name"] for f in data] if data else []


def get_screenshots(repo_name, branch, token):
    """Find screenshots anywhere under a known folder name."""
    data = http_json(
        "%s/repos/%s/%s/git/trees/%s?recursive=1" % (API, ORG, repo_name, branch), token
    )
    if not data:
        return []
    out = []
    for t in data.get("tree", []):
        p = t.get("path", "")
        if not p.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            continue
        parts = p.lower().split("/")
        if any(x in ("screenshots", "screenshot") for x in parts):
            out.append(p)
    out.sort()
    return out


def discover_icon(repo_name, branch, token, override=None):
    if override:
        return "%s/%s/%s/%s/%s" % (RAW, ORG, repo_name, branch, override.lstrip("/"))
    files = get_root_files(repo_name, branch, token)
    low = repo_name.lower()
    base = re.sub(r"-nusv$", "", low)  # "Syna-NUSV" -> "syna"
    cands = []
    for f in files:
        fl = f.lower()
        if not fl.endswith(".png"):
            continue
        if fl.startswith(ICON_PREFIXES) or fl.startswith(base) or fl.startswith(low):
            cands.append(f)
    if not cands:
        return None
    # last alphabetically: Syna_logo_2.png > Syna_logo.png
    best = max(cands)
    return "%s/%s/%s/%s/%s" % (RAW, ORG, repo_name, branch, best)


def fetch_releases(repo_name, token):
    data = http_json(
        "%s/repos/%s/%s/releases?per_page=8" % (API, ORG, repo_name), token
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
                        "count": a.get("download_count", 0),
                        "url": a.get("browser_download_url", ""),
                    }
                    for a in rel.get("assets", [])
                ],
            }
        )
    return out


def fetch_readme(repo_name, branch, token):
    url = "%s/%s/%s/%s/README.md" % (RAW, ORG, repo_name, branch)
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "nusv-site-sync")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            return None
        raise


# --------------------------------------------------------------------------
# Markdown subset renderer
# --------------------------------------------------------------------------

def resolve_ref(repo_name, branch, raw):
    raw = raw.strip()
    if raw.startswith(("http://", "https://", "#", "mailto:", "data:")):
        return raw
    raw = raw.lstrip("./")
    return "https://github.com/%s/%s/%s/%s" % (ORG, repo_name, branch, raw)


def resolve_raw(repo_name, branch, raw):
    raw = raw.strip()
    if raw.startswith(("http://", "https://", "data:")):
        return raw
    raw = raw.lstrip("./")
    return "%s/%s/%s/%s/%s" % (RAW, ORG, repo_name, branch, raw)


def md_inline(text, repo_name, branch):
    img_tokens = {}

    def img_placeholder(m):
        alt, src = m.group(1), m.group(2)
        key = "IMGTOK%d" % len(img_tokens)
        img_tokens[key] = (
            '<img src="%s" alt="%s" loading="lazy" referrerpolicy="no-referrer">'
            % (html.escape(resolve_raw(repo_name, branch, src), quote=True),
               html.escape(alt or "", quote=True))
        )
        return key

    def raw_img(m):
        tag = m.group(0)
        attrs, src = [], None
        for am in re.finditer(
            r"""\b(src|width|height|alt)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""",
            tag,
        ):
            k = am.group(1)
            val = am.group(2) if am.group(2) is not None else (
                am.group(3) if am.group(3) is not None else am.group(4)
            )
            if k == "src":
                src = html.escape(resolve_raw(repo_name, branch, val), quote=True)
            else:
                attrs.append('%s="%s"' % (k, html.escape(val, quote=True)))
        if src is None:
            return ""
        return '<img src="%s" loading="lazy" referrerpolicy="no-referrer" %s>' % (
            src,
            " ".join(attrs),
        )

    text = re.sub(r"<img\b[^>]*/?>", raw_img, text)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", img_placeholder, text
    )
    text = re.sub(r"`([^`]+)`", lambda m: "<code>%s</code>" % html.escape(m.group(1)), text)
    text = re.sub(r"\*\*([^*]+)\*\*", lambda m: "<strong>%s</strong>" % m.group(1), text)
    text = re.sub(r"__([^_]+)__", lambda m: "<strong>%s</strong>" % m.group(1), text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", lambda m: "<em>%s</em>" % m.group(1), text)

    def link(m):
        lab, dst = m.group(1), m.group(2)
        target = ' target="_blank" rel="noopener"' if dst.startswith("http") else ""
        return '<a href="%s"%s>%s</a>' % (
            html.escape(resolve_ref(repo_name, branch, dst), quote=True),
            target,
            lab,
        )

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", link, text)

    for key, val in img_tokens.items():
        text = text.replace(key, val)
    return text


def md_to_html(md, repo_name, branch):
    """Render a pragmatic README subset to HTML. Returns (html, dropped_first_h1)
    where dropped_first_h1 indicates the leading "# <repo title>" heading and any
    immediately following badge row were removed (they duplicate the page head)."""
    out = []
    lines = md.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    first_h1_dropped = False
    pending_h1_line = None

    while i < n:
        line = lines[i]

        # Drop the very first "# Title" heading of the README.
        m0 = re.match(r"^#\s+(.+?)\s*$", line)
        if not first_h1_dropped and m0:
            pending_h1_line = m0.group(1)
            first_h1_dropped = True
            i += 1
            # skip empty lines after the h1
            while i < n and lines[i].strip() == "":
                i += 1
            # skip the markdown badge lines / centered banner right after h1
            badge_start = i
            while i < n and (
                re.match(r"^\s*(<p align=\"center\">|\[!)", lines[i])
                or re.match(r"^\s*$", lines[i])
            ):
                i += 1
            # If what follows is clearly a list of links/images (badges row),
            # keep skipping until a real content line; otherwise rewind.
            if i > badge_start and i < n:
                pass
            continue

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
            out.append("<h%d>%s</h%d>" % (lvl, md_inline(m.group(2), repo_name, branch), lvl))
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
            inner = md_to_html("\n".join(quote), repo_name, branch)[0]
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
                    "".join("<li>%s</li>" % md_inline(it, repo_name, branch) for it in items),
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
                tbl.extend("<th>%s</th>" % md_inline(c, repo_name, branch) for c in head)
                tbl.append("</tr></thead><tbody>")
                for r in body:
                    cells = [c.strip() for c in r.strip("|").split("|")]
                    tbl.append("<tr>")
                    tbl.extend("<td>%s</td>" % md_inline(c, repo_name, branch) for c in cells)
                    tbl.append("</tr>")
                tbl.append("</tbody></table>")
                out.append("".join(tbl))
                continue
            out.append(md_inline(line, repo_name, branch))
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
        joined = " ".join(x.strip() for x in para)
        wrap = re.fullmatch(r"<p\b[^>]*>(.*)</p>", joined, re.S)
        if wrap:
            out.append('<div class="readme-img-block">%s</div>' % md_inline(wrap.group(1), repo_name, branch))
        else:
            out.append("<p>%s</p>" % md_inline(joined, repo_name, branch))

    return "\n".join(out), first_h1_dropped


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def human_size(num):
    num = num or 0
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return ("%.0f %s" % (num, unit)) if unit == "B" else ("%.1f %s" % (num, unit))
        num /= 1024.0
    return str(num)


def fmt_iso(iso):
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(
            datetime.timezone.utc
        )
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return (iso or "")[:10]


PLATFORM_BY_EXT = {
    ".apk": ("Android APK", ""),
    ".dmg": ("macOS (.dmg)", ""),
    ".msi": ("Windows (.msi)", ""),
    ".exe": ("Windows (.exe)", ""),
    ".deb": ("Linux (.deb)", ""),
    ".jar": ("Server / other (.jar)", "muted"),
    ".ipa": ("iOS (.ipa)", "muted"),
}


def card_markup(proj, kind="featured"):
    """Markup for listing cards (home "featured" or warehouse)."""
    icon = proj["icon_url"] or proj["fallback_icon"]
    icon_html = (
        '<span class="card-icon"><img src="%s" alt="%s icon" loading="lazy"></span>\n            '
        % (html.escape(icon, quote=True), html.escape(proj["name"]))
    )
    chips = "".join(
        '<span class="chip chip-accent">%s</span>' % html.escape(p) for p in proj["platforms"]
    )
    chips += '<span class="chip">%s</span>' % html.escape(proj["license"] or "Open source")
    links = []
    if kind == "featured":
        links.append('<a class="linkbtn" href="projects/%s.html">Project page</a>'
                     % proj["slug"])
        if proj["docs"]:
            links.append('<a class="linkbtn linkbtn-ghost" href="%s">Technical docs</a>'
                         % html.escape(proj["docs"], quote=True))
        else:
            links.append('<a class="linkbtn linkbtn-ghost" href="%s" target="_blank" rel="noopener">Repository</a>'
                         % html.escape(proj["repo_url"], quote=True))
    else:
        links.append('<a class="linkbtn" href="projects/%s.html">Project page</a>' % proj["slug"])
        if proj["docs"]:
            links.append('<a class="linkbtn linkbtn-ghost" href="%s">Technical docs</a>'
                         % html.escape(proj["docs"], quote=True))
        if proj["releases"]:
            links.append('<a class="linkbtn linkbtn-ghost" href="%s/releases" target="_blank" rel="noopener">Releases</a>'
                         % proj["repo_url"])
        else:
            links.append('<a class="linkbtn linkbtn-ghost" href="%s" target="_blank" rel="noopener">Source</a>'
                         % proj["repo_url"])
    return (
        '<div class="card reveal">\n'
        "          %s\n"
        '          <h3>%s</h3>\n'
        '          <p class="tagline">%s</p>\n'
        '          <div class="meta">%s</div>\n'
        '          <div class="card-links">\n'
        '            %s\n'
        "          </div>\n"
        "        </div>"
        % (icon_html, html.escape(proj["name"]), html.escape(proj["tagline"]),
           chips, "\n            ".join(links))
    )


def featured_section(projects):
    return "\n".join(card_markup(p, "featured") for p in projects)


def warehouse_section(projects):
    return "\n".join(card_markup(p, "warehouse") for p in projects)


def replace_markers(path, start_marker, end_marker, content):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if start_marker not in src or end_marker not in src:
        raise RuntimeError("markers missing in %s" % path)
    before = src.split(start_marker, 1)[0]
    after = src.split(end_marker, 1)[1]
    return before + start_marker + "\n" + content + "\n" + end_marker + after


def render_page(proj, readme_html, updated_utc):
    name, tagline = proj["name"], proj["tagline"]
    repo_url = proj["repo_url"]
    docs = proj["docs"]
    platforms, license_txt, stars, topics = (
        proj["platforms"], proj["license"], proj["stars"], proj["topics"]
    )
    icon = proj["icon_url"] or proj["fallback_icon"]

    chips = ["".join('<span class="chip chip-accent">%s</span>' % html.escape(p) for p in platforms)]
    if license_txt:
        chips.append('<span class="chip">%s</span>' % html.escape(license_txt))
    for t in topics[:5]:
        chips.append('<span class="chip">%s</span>' % html.escape(t))

    latest = proj["releases"][0] if proj["releases"] else None

    def dl_row(asset, big=False):
        label, kind = PLATFORM_BY_EXT.get(
            os.path.splitext(asset["name"].lower())[1], ("Download", "muted")
        )
        dl = ("%d downloads" % asset["count"]) if asset.get("count") else human_size(asset["size"])
        return (
            '<a class="dl-btn%s %s" href="%s" target="_blank" rel="noopener">'
            '<span class="dl-label">%s</span>'
            '<span class="dl-sub">%s &middot; %s</span></a>'
            % (" big" if big else "", kind, html.escape(asset["url"], quote=True),
               html.escape(label), html.escape(asset["name"]), dl)
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
    for rel in proj["releases"][1:]:
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
    info = []
    info.append('<div class="pg-info"><span>License</span><b>%s</b></div>' % html.escape(license_txt or "—"))
    info.append('<div class="pg-info"><span>Stars</span><b>%d</b></div>' % stars)
    info.append('<div class="pg-info"><span>Repository updated</span><b>%s</b></div>'
                % html.escape((proj.get("pushed_at") or "")[:10]))
    info.append('<div class="pg-info"><span>Source</span><a href="%s" target="_blank" rel="noopener">%s</a></div>'
                % (html.escape(repo_url, quote=True), html.escape(proj["repo"])))
    sidebar.append('<div class="card pg-side"><div class="side-title">Project info</div>%s</div>'
                   % "".join(info))

    # Screenshot gallery (optional, convention-based).
    gal = ""
    if proj["screenshots"]:
        imgs = "".join(
            '<a class="gal-item" href="%s" target="_blank" rel="noopener">'
            '<img src="%s" alt="Screenshot" loading="lazy" referrerpolicy="no-referrer"></a>'
            % (html.escape(resolve_raw(proj["repo"], proj["branch"], p), quote=True),
               html.escape(resolve_raw(proj["repo"], proj["branch"], p), quote=True))
            for p in proj["screenshots"][:8]
        )
        gal = '<h2 class="gal-title">Screenshots</h2><div class="gal">%s</div>' % imgs

    actions = ['<a class="btn btn-primary" href="#downloads">Download latest</a>']
    actions.append('<a class="btn btn-ghost" href="%s" target="_blank" rel="noopener">GitHub repository</a>' % html.escape(repo_url, quote=True))
    if docs:
        actions.append('<a class="btn btn-ghost" href="%s">Technical docs</a>' % html.escape(docs, quote=True))

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>%s — Downloads &amp; Introduction | United Science Vaca (NUSV)</title>
  <meta name="description" content="%s">
  <meta property="og:title" content="%s — NUSV">
  <meta property="og:description" content="%s">
  <meta property="og:image" content="%s">
  <meta property="og:type" content="website">
  <link rel="icon" type="image/png" href="../assets/img/nusv-logo.png">
  <link rel="stylesheet" href="../assets/css/style.css">
</head>
<body>

%s

  <main class="wrap">
    <nav class="pg-back"><a href="../warehouse.html">&#8249; All projects</a></nav>

    <article class="pg">

      <div class="pg-head">
        <div class="pg-head-main">
          <span class="pg-icon"><img src="%s" alt="%s icon" loading="lazy"></span>
          <h1>%s</h1>
          <p class="lede">%s</p>
          <div class="meta pg-chips">%s</div>
          <div class="btn-row pg-actions">
            %s
          </div>
        </div>
      </div>

      <div class="pg-grid">
        <section class="pg-about">
          <div class="pg-updated">README auto-synced from the repository &middot; %s UTC</div>
          %s
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
        html.escape(name),
        html.escape(tagline[:150], quote=True),
        html.escape(name),
        html.escape(tagline[:150], quote=True),
        html.escape(icon, quote=True),
        NAV,
        html.escape(icon, quote=True), html.escape(name), html.escape(name),
        html.escape(tagline),
        "".join(chips),
        "\n            ".join(actions),
        updated_utc,
        readme_html or "<p><em>No README yet — check the repository for details.</em></p>",
        gal,
        "".join(sidebar),
        FOOTER,
    )


# --------------------------------------------------------------------------
# Discovery + main
# --------------------------------------------------------------------------

def discover_projects(token):
    repos = list_org_repos(token) or []
    if not repos:
        return None  # signal: treat as failure (never wipe pages)

    projects = []
    for r in sorted(repos, key=lambda x: (x.get("name") or "").lower()):
        name = r.get("name")
        if r.get("fork"):
            continue
        if PROJECT_TOPIC not in get_topics(name, token):
            continue

        branch = r.get("default_branch") or "main"
        conf = get_site_json(name, branch, token)

        display = conf.get("name") or re.sub(r"-NUSV$", "", name, flags=re.I) or name
        desc = r.get("description") or ""
        tagline = conf.get("tagline") or desc
        platforms = conf.get("platforms") or []
        docs = conf.get("docs") or None  # site-relative or absolute URL
        license_txt = ((r.get("license") or {}) or {}).get("spdx_id")
        icon_url = discover_icon(name, branch, token, conf.get("icon"))
        screens = get_screenshots(name, branch, token)
        releases = fetch_releases(name, token) or []
        md = fetch_readme(name, branch, token)
        readme_html = md_to_html(md, name, branch)[0] if md else None

        projects.append(
            {
                "repo": name,
                "slug": conf.get("slug") or (
                    re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or name.lower()
                ),
                "name": display,
                "tagline": tagline,
                "platforms": platforms,
                "docs": docs,
                "license": license_txt,
                "repo_url": "https://github.com/%s/%s" % (ORG, name),
                "icon_url": icon_url,
                "fallback_icon": "https://avatars.githubusercontent.com/u/314111571",
                "branch": branch,
                "releases": releases,
                "screenshots": screens,
                "stars": r.get("stargazers_count", 0),
                "pushed_at": r.get("pushed_at", ""),
                "topics": conf.get("topics", []),
            }
        )
        print("discovered %s -> projects/%s.html" % (name, projects[-1]["slug"]))
    return projects


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=None)
    args = ap.parse_args()
    token = args.token or os.environ.get("NUSV_SYNC_TOKEN") or os.environ.get("GITHUB_TOKEN")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outdir = os.path.join(root, "projects")
    os.makedirs(outdir, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    stamp_re = re.compile(r'<div class="pg-updated">.*?</div>', re.S)

    def strip_stamp(t):
        return stamp_re.sub("", t)

    projects = discover_projects(token)
    if projects is None:
        print("ERROR: could not list organization repositories", file=sys.stderr)
        sys.exit(1)
    if not projects:
        print("WARNING: no repositories carry topic '%s' — nothing generated" % PROJECT_TOPIC)

    changed = []
    slugs = {p["slug"] for p in projects}

    # -- project pages --
    for proj in projects:
        md = fetch_readme(proj["repo"], proj["branch"], token)
        readme_html = md_to_html(md, proj["repo"], proj["branch"])[0] if md else None
        page = render_page(proj, readme_html, now)
        path = os.path.join(outdir, proj["slug"] + ".html")
        old = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                old = f.read()
        if strip_stamp(old) != strip_stamp(page):
            with open(path, "w", encoding="utf-8") as f:
                f.write(page)
            changed.append("projects/%s.html" % proj["slug"])
        print("synced %s" % proj["slug"])

    # -- remove pages for projects that are no longer discovered --
    for f in os.listdir(outdir):
        if not f.endswith(".html"):
            continue
        if f[:-5] not in slugs:
            os.remove(os.path.join(outdir, f))
            changed.append("projects/%s.html (removed)" % f)
            print("removed stale %s" % f)

    # -- listing pages (marker regions) --
    def patch_file(path, start, end, section):
        try:
            patched = replace_markers(path, start, end, section)
        except RuntimeError as e:
            print("SKIP %s: %s" % (os.path.basename(path), e))
            return
        with open(path, "r", encoding="utf-8") as f:
            current = f.read()
        if patched != current:
            with open(path, "w", encoding="utf-8") as f:
                f.write(patched)
            changed.append(os.path.basename(path))

    patch_file(INDEX_FEATURED, FEAT_START, FEAT_END, featured_section(projects))
    patch_file(WAREHOUSE, WH_START, WH_END, warehouse_section(projects))

    print("changed: %s" % (", ".join(changed) if changed else "none"))
    sys.exit(0)


if __name__ == "__main__":
    main()
