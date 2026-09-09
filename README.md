# NUSV.github.io

The official website of **United Science Vaca (NUSV)**, built as a static site and served from GitHub Pages at [nusv.github.io](https://nusv.github.io).

## How the site stays fresh

A GitHub Actions workflow ([`.github/workflows/sync.yml`](.github/workflows/sync.yml)) runs [tools/sync_data.py](tools/sync_data.py) every 6 hours (and on manual dispatch) to:

1. list every repository in the NUSV organization,
2. pick the ones tagged with the topic **`nusv-project`**,
3. regenerate each project page under `projects/` (README introduction, latest releases, downloads, auto-discovered icon, optional screenshots),
4. refresh the listings on `index.html` (featured grid) and `warehouse.html` — only the marker regions `<!-- …-GRID:start/end -->` are rewritten; hand-written copy is preserved.

Only changes are committed; an unchanged run pushes nothing.

## Adding a new project (no website edits needed)

1. Create a repository in the NUSV organization (or transfer an existing one), public.
2. Tag it with the project topic:
   ```bash
   gh repo edit NUSV/your-repo --add-topic nusv-project
   ```
3. Optional, for a nicer listing — add `site.json` in the repo root:
   ```json
   {
     "slug": "friendly-page-url",
     "name": "Display Name",
     "tagline": "One-line description for cards and the page header.",
     "platforms": ["Android", "Windows"],
     "docs": "/docs/your-repo.html",
     "icon": "path/inside/repo.png"
   }
   ```
   Without `site.json` the generator falls back to the repository description, the repository name (minus a trailing `-NUSV`), and no platform chips.
4. The page icon is auto-discovered: any `*.png` in the repo root named like the repo or starting with `logo`/`icon` (the last one alphabetically wins). To add a screenshot gallery, put images under `screenshots/`, `docs/screenshots/` or `assets/screenshots/`.

That's it. The next scheduled sync (or a manual *Run workflow* on the [Sync project data](https://github.com/NUSV/NUSV.github.io/actions/workflows/sync.yml) action) adds the project page and listing cards. To trigger a sync instantly from a release pipeline:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/NUSV/NUSV.github.io/dispatches \
  -d '{"event_type":"sync-projects"}'
```

Removing the topic removes the project from the website on the next sync. Infrastructure repositories (`.github`, `NUSV.github.io`, `nusv-lite-sync`, forks) never carry the topic, so they stay off the listings automatically.

## Pages

| File | Purpose |
| --- | --- |
| `index.html` | Home — hero, stats; the featured grid is generated |
| `warehouse.html` | Warehouse — generated project cards + hand-written intro |
| `docs.html` | Hand-written technical-docs hub |
| `docs/syna.html`, `docs/nusv-lite.html`, `docs/gomoku.html` | Hand-written deep technical docs (architecture, protocol, builds) |
| `projects/<slug>.html` | **Generated** per-project pages (intro + downloads) |
| `about.html`, `404.html` | Static pages |
| `tools/sync_data.py` | The generator (pure Python 3 stdlib, no dependencies) |

## Editing

No build step for the hand-written pages: edit the HTML directly; styling lives in `assets/css/style.css`, scripts in `assets/js/main.js`, brand assets in `assets/img/`. Push to `main` — GitHub Pages deploys automatically.

## Adding a language (i18n)

The site is English-first by design. To add translations later:

1. Give elements a `data-i18n` key.
2. Define overrides as `window.I18N["zh"] = { key: "值" }` in `assets/js/main.js`.
3. Call `setLang("zh")` (the language toggle already calls `setLang`).

English is served inline so the site remains fully readable without JavaScript.

## License

MIT — see the [NUSV organization](https://github.com/NUSV) for details.
