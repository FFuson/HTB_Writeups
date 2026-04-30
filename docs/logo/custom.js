/**
 * rootea.es — JS custom sobre Mintlify.
 * Servido via jsdelivr (cache 12h).
 *
 * Funcionalidades:
 *   - Tabla maestra ordenable (click en cabeceras).
 *   - Filtros por chips en /all (OS y dificultad).
 *   - Charts client-side (distribución por OS y dificultad).
 *   - Marcador de TOC con scroll-spy reforzado.
 */

(function () {
  "use strict";

  // ────────────────────────────────────────────────────────────
  // Tabla ordenable (todas las páginas con tablas)
  // ────────────────────────────────────────────────────────────
  function attachSorters() {
    document.querySelectorAll("main table").forEach(function (table) {
      table.querySelectorAll("th").forEach(function (th, idx) {
        if (th.dataset.rooteaSort) return;
        th.dataset.rooteaSort = "1";
        th.style.cursor = "pointer";
        th.title = "Click para ordenar";
        let asc = true;
        th.addEventListener("click", function () {
          const tbody = table.tBodies[0];
          if (!tbody) return;
          const rows = Array.from(tbody.rows);
          rows.sort(function (a, b) {
            const v1 = a.cells[idx].innerText.trim();
            const v2 = b.cells[idx].innerText.trim();
            const n1 = parseFloat(v1.replace(/[^0-9.-]/g, ""));
            const n2 = parseFloat(v2.replace(/[^0-9.-]/g, ""));
            if (!isNaN(n1) && !isNaN(n2)) return asc ? n1 - n2 : n2 - n1;
            return asc
              ? v1.localeCompare(v2, undefined, { numeric: true })
              : v2.localeCompare(v1, undefined, { numeric: true });
          });
          rows.forEach(function (row) { tbody.appendChild(row); });
          asc = !asc;
        });
      });
    });
  }

  // ────────────────────────────────────────────────────────────
  // Charts en /all (Chart.js cargado bajo demanda)
  // ────────────────────────────────────────────────────────────
  const CHART_JS_URL =
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js";

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      const s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  async function fetchMachines() {
    const tryUrls = [
      "/api/machines.json",
      "https://cdn.jsdelivr.net/gh/FFuson/HTB_Writeups@main/data/machines.json",
    ];
    for (const url of tryUrls) {
      try {
        const r = await fetch(url, { cache: "force-cache" });
        if (r.ok) return await r.json();
      } catch (e) { /* try next */ }
    }
    return [];
  }

  function isAllPage() {
    return /(^|\/)(en\/)?all\/?$/.test(location.pathname);
  }

  const PALETTE = ["#9FEF00", "#00E5FF", "#FFC400", "#FF8A00", "#FF003C"];

  async function renderCharts() {
    if (!isAllPage()) return;
    const slot = document.getElementById("rootea-charts");
    if (!slot) return;

    let machines = [];
    try { machines = await fetchMachines(); }
    catch (e) { return; }
    if (!machines.length) return;

    try { await loadScript(CHART_JS_URL); }
    catch (e) { return; }

    const Chart = window.Chart;
    if (!Chart) return;

    Chart.defaults.color = "#a1a1aa";
    Chart.defaults.font.family =
      'ui-monospace, "SFMono-Regular", "JetBrains Mono", Menlo, monospace';
    Chart.defaults.borderColor = "rgba(159, 239, 0, 0.12)";

    // 1. Pie por OS
    const byOs = {};
    machines.forEach(function (m) {
      const k = m.os || "Other";
      byOs[k] = (byOs[k] || 0) + 1;
    });

    const osCanvas = document.getElementById("chart-os");
    if (osCanvas) {
      new Chart(osCanvas, {
        type: "doughnut",
        data: {
          labels: Object.keys(byOs),
          datasets: [{
            data: Object.values(byOs),
            backgroundColor: PALETTE,
            borderColor: "#0A0E0A",
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 12 } },
          },
          cutout: "60%",
        },
      });
    }

    // 2. Bar por dificultad
    const DIFF_ORDER = ["Fácil", "Medio", "Difícil", "Insano"];
    const byDiff = { "Fácil": 0, "Medio": 0, "Difícil": 0, "Insano": 0 };
    machines.forEach(function (m) {
      const k = m.difficulty || "Fácil";
      if (k in byDiff) byDiff[k]++;
    });

    const diffCanvas = document.getElementById("chart-difficulty");
    if (diffCanvas) {
      new Chart(diffCanvas, {
        type: "bar",
        data: {
          labels: DIFF_ORDER,
          datasets: [{
            data: DIFF_ORDER.map(function (k) { return byDiff[k]; }),
            backgroundColor: ["#9FEF00", "#FFC400", "#FF8A00", "#FF003C"],
            borderWidth: 0,
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { precision: 0 } },
            x: { grid: { display: false } },
          },
        },
      });
    }

    // 3. Bar por año de retirada
    const byYear = {};
    machines.forEach(function (m) {
      const y = (m.release_date || "").slice(0, 4);
      if (y) byYear[y] = (byYear[y] || 0) + 1;
    });
    const years = Object.keys(byYear).sort();
    const yearCanvas = document.getElementById("chart-year");
    if (yearCanvas && years.length) {
      new Chart(yearCanvas, {
        type: "line",
        data: {
          labels: years,
          datasets: [{
            data: years.map(function (y) { return byYear[y]; }),
            borderColor: "#9FEF00",
            backgroundColor: "rgba(159, 239, 0, 0.18)",
            tension: 0.3,
            fill: true,
            pointBackgroundColor: "#9FEF00",
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { precision: 0 } },
          },
        },
      });
    }
  }

  // ────────────────────────────────────────────────────────────
  // Filtros chips para /all
  // ────────────────────────────────────────────────────────────
  function attachFilters() {
    if (!isAllPage()) return;
    const chips = document.querySelectorAll(".rootea-chip");
    if (!chips.length) return;

    function applyFilters() {
      const activeOs = new Set();
      const activeDiff = new Set();
      chips.forEach(function (c) {
        if (!c.classList.contains("active")) return;
        if (c.dataset.filterType === "os") activeOs.add(c.dataset.filterValue);
        if (c.dataset.filterType === "diff") activeDiff.add(c.dataset.filterValue);
      });

      const tables = document.querySelectorAll("main table");
      tables.forEach(function (table) {
        const tbody = table.tBodies[0];
        if (!tbody) return;
        // Detectar la sección OS leyendo el H2 anterior a la tabla
        let osLabel = "";
        let prev = table.previousElementSibling;
        while (prev) {
          if (prev.tagName === "H2") {
            osLabel = prev.innerText.trim().split(/\s/)[0].toLowerCase();
            break;
          }
          prev = prev.previousElementSibling;
        }

        const matchOs = activeOs.size === 0
          ? true
          : Array.from(activeOs).some(function (v) {
              return osLabel.startsWith(v.toLowerCase());
            });

        Array.from(tbody.rows).forEach(function (tr) {
          const diffCell = tr.cells[1] ? tr.cells[1].innerText : "";
          const matchDiff = activeDiff.size === 0
            ? true
            : Array.from(activeDiff).some(function (v) {
                return diffCell.toLowerCase().includes(v.toLowerCase());
              });
          if (matchOs && matchDiff) tr.classList.remove("rootea-hidden");
          else tr.classList.add("rootea-hidden");
        });
      });
    }

    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        // Toggle dentro del mismo grupo (multi-selección)
        c.classList.toggle("active");
        applyFilters();
      });
    });
  }

  // ────────────────────────────────────────────────────────────
  // TOC scroll-spy con marcador animado (refuerzo del nativo)
  // ────────────────────────────────────────────────────────────
  function attachScrollSpy() {
    const links = document.querySelectorAll(
      'nav[aria-label*="page" i] a, .in-this-page a'
    );
    if (!links.length) return;

    const headings = Array.from(document.querySelectorAll(
      "main h2, main h3"
    )).filter(function (h) { return h.id; });
    if (!headings.length) return;

    function update() {
      const scrollTop = window.scrollY + 100;
      let active = headings[0];
      for (const h of headings) {
        if (h.offsetTop <= scrollTop) active = h;
        else break;
      }
      if (!active) return;
      links.forEach(function (a) {
        const href = a.getAttribute("href") || "";
        const matches = href.endsWith("#" + active.id);
        if (matches) a.setAttribute("data-active", "true");
        else a.removeAttribute("data-active");
      });
    }

    window.addEventListener("scroll", update, { passive: true });
    update();
  }

  // ────────────────────────────────────────────────────────────
  // Inicialización
  // ────────────────────────────────────────────────────────────
  function init() {
    attachSorters();
    attachFilters();
    renderCharts();
    attachScrollSpy();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Re-ejecutar tras navegación SPA de Mintlify
  let lastPath = location.pathname;
  setInterval(function () {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      setTimeout(init, 200);
    }
  }, 500);
})();
