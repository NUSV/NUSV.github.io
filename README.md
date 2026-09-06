# NUSV.github.io

The official website of **United Science Vaca (NUSV)**, built as a static site and served from GitHub Pages at [nusv.github.io](https://nusv.github.io).

## Pages

| File | Purpose |
| --- | --- |
| `index.html` | Home — hero, project highlights, stats |
| `warehouse.html` | Warehouse — every project with downloads, source and docs links |
| `docs.html` | Docs index — project guides |
| `docs/syna.html` | Syna guide (overview / problem / highlights / links) |
| `docs/nusv-lite.html` | NUSV LITE guide |
| `docs/gomoku.html` | Gomoku-NUSV guide |
| `about.html` | About USV |
| `404.html` | Not-found page |

## Editing

No build step. Edit the HTML directly; styling lives in `assets/css/style.css`, scripts in `assets/js/main.js`, and imagery in `assets/img/`. Push to `main` — GitHub Pages deploys automatically.

## Adding a language (i18n)

The site is English-first by design. To add translations later:

1. Give elements a `data-i18n` key.
2. Define overrides as `window.I18N["zh"] = { key: "值" }` in `assets/js/main.js`.
3. Call `setLang("zh")` (the language toggle already calls `setLang`).

English is served inline so the site remains fully readable without JavaScript.

## License

MIT — see the [NUSV organization](https://github.com/NUSV) for details.
