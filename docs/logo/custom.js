/**
 * rootea.es — JS custom sobre Mintlify.
 * Mintlify lo auto-carga por ser un .js del directorio de docs y lo
 * inlinea en la página; no hay <script src> a ningún CDN.
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
  // Tabla ordenable — IntersectionObserver para inicialización
  // perezosa (solo se setup cuando la tabla entra en viewport,
  // evitando coste inicial en páginas largas con muchas tablas).
  // ────────────────────────────────────────────────────────────
  function setupTable(table) {
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
        const frag = document.createDocumentFragment();
        rows.forEach(function (row) { frag.appendChild(row); });
        tbody.appendChild(frag);
        asc = !asc;
      });
    });
  }

  function attachSorters() {
    const tables = document.querySelectorAll("main table");
    if (!tables.length) return;
    if (!("IntersectionObserver" in window)) {
      tables.forEach(setupTable);
      return;
    }
    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          setupTable(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: "200px" });
    tables.forEach(function (t) { io.observe(t); });
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
  // Filtros chips para /all (OS, dificultad, vector)
  // ────────────────────────────────────────────────────────────
  function slugifyName(name) {
    return name
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/ñ/g, "n")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  async function attachFilters() {
    if (!isAllPage()) return;
    const chips = document.querySelectorAll(".rootea-chip");
    if (!chips.length) return;

    // Construir mapa nombre→vector desde el catálogo
    let vectorByName = {};
    try {
      const m = await fetchMachines();
      m.forEach(function (x) {
        vectorByName[slugifyName(x.name)] = x.primary_vector || "";
      });
    } catch (e) { /* sin catálogo, filtros de vector inertes */ }

    function applyFilters() {
      const activeOs = new Set();
      const activeDiff = new Set();
      const activeVector = new Set();
      chips.forEach(function (c) {
        if (!c.classList.contains("active")) return;
        if (c.dataset.filterType === "os") activeOs.add(c.dataset.filterValue);
        if (c.dataset.filterType === "diff") activeDiff.add(c.dataset.filterValue);
        if (c.dataset.filterType === "vector") activeVector.add(c.dataset.filterValue);
      });

      const tables = document.querySelectorAll("main table");
      tables.forEach(function (table) {
        const tbody = table.tBodies[0];
        if (!tbody) return;

        // OS de la sección, leído del H2 previo
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

          // Nombre vía link de la primera celda → slug → mapa de vector
          let vectorOk = true;
          if (activeVector.size > 0) {
            const link = tr.cells[0] ? tr.cells[0].querySelector("a") : null;
            const slug = link
              ? link.getAttribute("href").split("/").pop()
              : slugifyName(tr.cells[0].innerText.trim());
            const v = vectorByName[slug] || "";
            vectorOk = activeVector.has(v);
          }

          if (matchOs && matchDiff && vectorOk) tr.classList.remove("rootea-hidden");
          else tr.classList.add("rootea-hidden");
        });
      });
    }

    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        c.classList.toggle("active");
        applyFilters();
      });
    });
  }

  // ────────────────────────────────────────────────────────────
  // TOC scroll-spy con marcador animado (refuerzo del nativo)
  //   - rAF coalescing (1 cálculo por frame, no por scroll event)
  //   - cache de offsets (recalculado en resize/load, no en scroll)
  //   - búsqueda binaria sobre offsets ordenados
  //   - actualización DOM sólo cuando cambia el activo (no cada frame)
  // ────────────────────────────────────────────────────────────
  let scrollSpyState = null;

  function attachScrollSpy() {
    // Limpiar cualquier instancia previa (SPA navigation)
    if (scrollSpyState) {
      window.removeEventListener("scroll", scrollSpyState.onScroll);
      window.removeEventListener("resize", scrollSpyState.onResize);
      scrollSpyState = null;
    }

    const links = document.querySelectorAll(
      'nav[aria-label*="page" i] a, .in-this-page a'
    );
    if (!links.length) return;

    const headings = Array.from(document.querySelectorAll(
      "main h2, main h3"
    )).filter(function (h) { return h.id; });
    if (!headings.length) return;

    // Cache de offsets — sólo se lee del DOM aquí.
    let offsets = [];
    function recomputeOffsets() {
      offsets = headings.map(function (h) { return h.offsetTop; });
    }
    recomputeOffsets();

    // Mapa link-href → elemento (precomputado, evita query en cada scroll)
    const linkByHash = {};
    links.forEach(function (a) {
      const href = a.getAttribute("href") || "";
      const i = href.indexOf("#");
      if (i >= 0) {
        const id = href.slice(i + 1);
        if (id) linkByHash[id] = a;
      }
    });

    let lastActiveId = null;
    let ticking = false;

    function compute() {
      ticking = false;
      const scrollTop = window.scrollY + 100;
      // Búsqueda binaria — encuentra el último heading con offsetTop ≤ scrollTop
      let lo = 0;
      let hi = offsets.length - 1;
      let activeIdx = 0;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (offsets[mid] <= scrollTop) {
          activeIdx = mid;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }
      const activeId = headings[activeIdx].id;
      if (activeId === lastActiveId) return;

      // Sólo aquí tocamos el DOM, una vez por cambio
      if (lastActiveId && linkByHash[lastActiveId]) {
        linkByHash[lastActiveId].removeAttribute("data-active");
      }
      if (linkByHash[activeId]) {
        linkByHash[activeId].setAttribute("data-active", "true");
      }
      lastActiveId = activeId;
    }

    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(compute);
    }

    function onResize() {
      recomputeOffsets();
      onScroll();
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize, { passive: true });
    scrollSpyState = { onScroll: onScroll, onResize: onResize };
    compute();
  }

  // ────────────────────────────────────────────────────────────
  // Filtro live del glosario (input → ocultar h3 + sus hermanos
  // hasta el próximo h2/h3 según el query). Cero coste si la
  // página no es el glosario.
  //
  // Robusto frente a la hidratación tardía de Mintlify (reintenta
  // hasta 10 veces) y al hecho de que <main> a veces no envuelve el
  // contenido (busca H3 globalmente).
  // ────────────────────────────────────────────────────────────
  let glosarioState = null;

  function setupGlosarioFilter() {
    let tries = 0;

    function attempt() {
      // El selector por clase es más seguro que el por id en SSR
      // de Mintlify; el id se conserva como fallback.
      const input =
        document.querySelector(".rootea-glosario-filter") ||
        document.getElementById("rootea-glosario-filter");

      if (!input) {
        if (tries++ < 10) {
          window.setTimeout(attempt, 250);
        } else {
          glosarioState = null;
        }
        return;
      }

      const empty =
        document.querySelector(".rootea-glosario-empty") ||
        document.getElementById("rootea-glosario-empty");

      // Buscar h3 globalmente — Mintlify a veces no usa <main>.
      const allH3 = document.querySelectorAll("h3");
      if (!allH3.length) {
        if (tries++ < 10) window.setTimeout(attempt, 250);
        return;
      }

      // Construir secciones por sibling-walk a partir de cada h3.
      const sections = [];
      allH3.forEach(function (h3) {
        // Saltar h3 que estén en sidebars / TOC / nav (sólo queremos
        // los del cuerpo del artículo).
        if (h3.closest("nav, aside, header, footer")) return;
        const nodes = [h3];
        let cur = h3.nextElementSibling;
        while (cur && cur.tagName !== "H2" && cur.tagName !== "H3") {
          nodes.push(cur);
          cur = cur.nextElementSibling;
        }
        const text = nodes
          .map(function (n) { return n.textContent || ""; })
          .join(" ")
          .toLowerCase();
        sections.push({ nodes: nodes, text: text });
      });

      if (!sections.length) return;

      function applyFilter() {
        const q = (input.value || "").trim().toLowerCase();
        let visible = 0;
        sections.forEach(function (s) {
          const match = !q || s.text.indexOf(q) !== -1;
          if (match) visible++;
          s.nodes.forEach(function (n) {
            if (match) n.classList.remove("rootea-filter-hidden");
            else n.classList.add("rootea-filter-hidden");
          });
        });
        if (empty) {
          if (q && visible === 0) empty.classList.add("visible");
          else empty.classList.remove("visible");
        }
      }

      // Despegar listener anterior (SPA navigation re-runs init).
      if (glosarioState && glosarioState.input && glosarioState.handler) {
        const prev = glosarioState;
        prev.input.removeEventListener("input", prev.handler);
        prev.input.removeEventListener("keyup", prev.handler);
        prev.input.removeEventListener("change", prev.handler);
      }
      // Triple-bind: cubre browsers/IME que no disparan `input`
      // limpiamente. El handler es idempotente.
      input.addEventListener("input", applyFilter);
      input.addEventListener("keyup", applyFilter);
      input.addEventListener("change", applyFilter);
      glosarioState = { input: input, handler: applyFilter };
    }

    attempt();
  }

  // ────────────────────────────────────────────────────────────
  // Giscus embed loader — busca <div data-giscus-term="..."> y
  // monta el script de Giscus dinámicamente. Hace fail-soft: si no
  // hay slots o si Giscus está bloqueado por adblock, el sitio
  // sigue funcionando.
  // ────────────────────────────────────────────────────────────
  const GISCUS_REPO = "FFuson/HTB_Writeups";
  const GISCUS_REPO_ID = "R_kgDOSQQ2XA";
  const GISCUS_CATEGORY = "General";
  const GISCUS_CATEGORY_ID = "DIC_kwDOSQQ2XM4C8Cuo";

  function loadGiscusEmbeds() {
    const slots = document.querySelectorAll("[data-giscus-term]");
    if (!slots.length) return;

    slots.forEach(function (slot) {
      if (slot.dataset.giscusLoaded === "1") return;
      const term = slot.dataset.giscusTerm || "";
      if (!term) return;
      const lang = slot.dataset.giscusLang === "en" ? "en" : "es";

      // Limpiar contenido previo (para SPA re-mount).
      slot.innerHTML = "";

      const s = document.createElement("script");
      s.src = "https://giscus.app/client.js";
      s.async = true;
      s.crossOrigin = "anonymous";
      const attrs = {
        "data-repo": GISCUS_REPO,
        "data-repo-id": GISCUS_REPO_ID,
        "data-category": GISCUS_CATEGORY,
        "data-category-id": GISCUS_CATEGORY_ID,
        "data-mapping": "specific",
        "data-term": term,
        "data-strict": "0",
        "data-reactions-enabled": "1",
        "data-emit-metadata": "0",
        "data-input-position": "bottom",
        "data-theme": "noborder_dark",
        "data-lang": lang,
        "data-loading": "lazy",
      };
      Object.keys(attrs).forEach(function (k) {
        s.setAttribute(k, attrs[k]);
      });

      slot.appendChild(s);
      slot.dataset.giscusLoaded = "1";
    });
  }

  // ────────────────────────────────────────────────────────────
  // Inicialización
  // ────────────────────────────────────────────────────────────
  function init() {
    attachSorters();
    attachFilters();
    renderCharts();
    attachScrollSpy();
    setupGlosarioFilter();
    loadGiscusEmbeds();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Re-ejecutar tras navegación SPA de Mintlify — usar
  // history API en lugar de polling (cero coste idle).
  let lastPath = location.pathname;
  function onRoute() {
    if (location.pathname === lastPath) return;
    lastPath = location.pathname;
    setTimeout(init, 200);
  }
  ["pushState", "replaceState"].forEach(function (fn) {
    const orig = history[fn];
    history[fn] = function () {
      const r = orig.apply(this, arguments);
      window.dispatchEvent(new Event("rooteanav"));
      return r;
    };
  });
  window.addEventListener("popstate", onRoute);
  window.addEventListener("rooteanav", onRoute);

  // Mintlify hidrata el MDX después de DOMContentLoaded, así que
  // los slots de giscus aparecen tarde. Observer que dispara el
  // loader en cuanto un slot pendiente aparece en el DOM. El loader
  // es idempotente (skipea slots con data-giscus-loaded="1").
  if (typeof MutationObserver !== "undefined") {
    const obs = new MutationObserver(function () {
      const pending = document.querySelector(
        "[data-giscus-term]:not([data-giscus-loaded='1'])"
      );
      if (pending) loadGiscusEmbeds();
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }
})();
