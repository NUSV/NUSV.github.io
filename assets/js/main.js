// United Science Vaca — site scripts
// i18n: English is served inline as the source language; assets/js/i18n.js
// carries the translations. Elements opt in with data-i18n="key"; the page
// <html> tag can carry data-i18n-title="key" (+ data-i18n-args) to translate
// document.title. Placeholders {n} / {name} / {doc} are filled from
// data-i18n-args.

(function () {
  "use strict";

  // ---- active nav state ----
  const path = window.location.pathname.split("/").filter(Boolean);
  const current = path[path.length - 1] || "index.html";
  const section = path[path.length - 2] || "";

  const navMap = {
    "index.html": "index.html",
    warehouse: "warehouse.html",
    docs: "docs.html",
    about: "about.html",
    "404.html": "index.html",
    projects: "warehouse.html",
    mirror: "docs.html",
  };

  const activeHref = navMap[current] || navMap[section] || "index.html";

  document.querySelectorAll(".nav-links a").forEach(function (a) {
    if (a.getAttribute("href") === activeHref) a.classList.add("active");
  });

  // ---- card spotlight ----
  document.querySelectorAll(".card").forEach(function (card) {
    card.addEventListener("pointermove", function (e) {
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", ((e.clientX - r.left) / r.width) * 100 + "%");
      card.style.setProperty("--my", ((e.clientY - r.top) / r.height) * 100 + "%");
    });
  });

  // ---- reveal on scroll ----
  const observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.08 }
  );

  document.querySelectorAll(".reveal").forEach(function (el) {
    observer.observe(el);
  });

  document.querySelectorAll(".footer .year").forEach(function (el) {
    el.textContent = new Date().getFullYear();
  });

  // ---- i18n ----
  const I18N = window.I18N || {};
  const STORE_KEY = "nusv-lang";
  const orig = new Map();

  function fill(value, el) {
    if (value == null) return "";
    const args = el.dataset.i18nArgs;
    if (args === undefined) return value;
    return value
      .replace(/\{n\}/g, args)
      .replace(/\{name\}/g, args)
      .replace(/\{doc\}/g, args);
  }

  function applyLang(lang) {
    const d = I18N[lang] || null;

    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      if (!orig.has(el)) orig.set(el, el.innerHTML);
      const val = d ? d[el.dataset.i18n] : undefined;
      el.innerHTML = val !== undefined ? fill(val, el) : orig.get(el);
    });

    const html = document.documentElement;
    if (html.dataset.i18nTitle) {
      if (!orig.has(html)) orig.set(html, document.title);
      const val = d ? d[html.dataset.i18nTitle] : undefined;
      document.title = val !== undefined ? fill(val, html) : orig.get(html);
    }

    html.lang = lang === "zh" ? "zh-CN" : "en";

    const toggle = document.getElementById("lang-toggle");
    if (toggle) {
      toggle.dataset.lang = lang;
      toggle.textContent = lang === "zh" ? "EN" : "中文";
      toggle.title = lang === "zh" ? "Switch to English" : "切换到中文";
    }
  }

  window.setLang = function (lang) {
    const next = lang === "zh" ? "zh" : "en";
    applyLang(next);
    try {
      localStorage.setItem(STORE_KEY, next);
    } catch (e) {
      /* storage unavailable (private mode) — ignore */
    }
    try {
      const url = new URL(window.location.href);
      if (next === "en") url.searchParams.delete("lang");
      else url.searchParams.set("lang", next);
      history.replaceState(null, "", url);
    } catch (e) {
      /* history unavailable — ignore */
    }
  };

  let saved = null;
  try {
    saved = localStorage.getItem(STORE_KEY);
  } catch (e) {
    saved = null;
  }

  let fromUrl = null;
  try {
    fromUrl = new URLSearchParams(window.location.search).get("lang");
  } catch (e) {
    fromUrl = null;
  }

  const initial =
    fromUrl === "zh" || fromUrl === "en"
      ? fromUrl
      : saved === "zh"
        ? "zh"
        : "en";
  applyLang(initial);

  const toggle = document.getElementById("lang-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      window.setLang(toggle.dataset.lang === "zh" ? "en" : "zh");
    });
  }
})();
