// United Science Vaca — site scripts
// i18n note: English is the source language. To add a language later,
// set window.I18N[lang] and call setLang(lang) (see toggle stub below).

(function () {
  "use strict";

  const navMark = document.querySelectorAll(".nav-links a");
  const current = window.location.pathname.split("/").pop() || "index.html";

  navMark.forEach(function (a) {
    if (a.getAttribute("href") === current) a.classList.add("active");
  });

  document.querySelectorAll(".card").forEach(function (card) {
    card.addEventListener("pointermove", function (e) {
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", ((e.clientX - r.left) / r.width) * 100 + "%");
      card.style.setProperty("--my", ((e.clientY - r.top) / r.height) * 100 + "%");
    });
  });

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

  window.setLang = function (lang) {
    // English is served inline; translations will be provided as
    // window.I18N[lang] overrides (data-i18n keys) in a future update.
    if (lang !== "en" && !window.I18N[lang]) {
      const note = document.getElementById("i18n-note");
      if (note) note.style.display = "block";
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
