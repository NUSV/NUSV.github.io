// United Science Vaca — site scripts
// i18n note: English is the source language. To add a language later,
// set window.I18N[lang] and call setLang(lang) (see toggle below).

(function () {
  "use strict";

  // Active nav state: exact page, or section prefixes
  // (projects/ pages belong to Warehouse, docs/ pages belong to Docs).
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
  };

  const activeHref =
    navMap[current] || navMap[section] || "index.html";

  document.querySelectorAll(".nav-links a").forEach(function (a) {
    if (a.getAttribute("href") === activeHref) a.classList.add("active");
  });

  // Card spotlight follows the pointer.
  document.querySelectorAll(".card").forEach(function (card) {
    card.addEventListener("pointermove", function (e) {
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", ((e.clientX - r.left) / r.width) * 100 + "%");
      card.style.setProperty("--my", ((e.clientY - r.top) / r.height) * 100 + "%");
    });
  });

  // Reveal-on-scroll.
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

  window.I18N = {};

  // Floating feedback so the language toggle never feels dead.
  function toast(message) {
    const old = document.querySelector(".toast");
    if (old) old.remove();
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(function () {
      el.classList.add("out");
      setTimeout(function () {
        el.remove();
      }, 350);
    }, 2600);
  }

  window.setLang = function (lang) {
    // English is served inline; translations will be provided as
    // window.I18N[lang] overrides (data-i18n keys) in a future update.
    if (lang !== "en" && !window.I18N[lang]) {
      toast("中文版即将推出 — Chinese translation coming soon");
    }
  };

  const toggle = document.getElementById("lang-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      const next = toggle.dataset.lang === "zh" ? "en" : "zh";
      toggle.dataset.lang = next;
      setLang(next);
    });
  }
})();
