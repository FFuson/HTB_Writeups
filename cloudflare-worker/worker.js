/**
 * Cloudflare Worker para rootea.es
 * ──────────────────────────────────
 * Sirve endpoints que Mintlify no puede generar:
 *
 *   GET /random         → 302 a una máquina aleatoria del catálogo
 *   GET /api/machines.json → JSON cacheado del catálogo
 *   GET /feed.xml       → RSS 2.0 con las últimas 30 máquinas
 *   GET /og/*           → imagen Open Graph dinámica por máquina
 *
 * Cualquier otra ruta pasa transparente al origin (Mintlify).
 *
 * Configuración recomendada:
 *   - Route: rootea.es/* → este worker
 *   - Variable MACHINES_URL = URL raw de machines.json en GitHub
 */

const MACHINES_URL =
  "https://raw.githubusercontent.com/FFuson/HTB_Writeups/main/data/machines.json";

const SEO_INDEX_URL =
  "https://raw.githubusercontent.com/FFuson/HTB_Writeups/main/data/seo_index.json";

const HREFLANG_URL =
  "https://raw.githubusercontent.com/FFuson/HTB_Writeups/main/data/hreflang.json";

const SITE_URL = "https://rootea.es";
const CACHE_TTL = 60 * 60; // 1h

// robots.txt servido por el Worker (versionado en git), con prioridad sobre el
// de Mintlify y sobre la feature "Manage robots.txt" de Cloudflare. Política:
// DIFUSIÓN MÁXIMA — se da la bienvenida a TODOS los crawlers, incluidos los de
// IA (búsqueda Y entrenamiento), para maximizar presencia en buscadores y en
// respuestas de LLMs. El contenido original (glosario, metodología, AD CS,
// etc.) está pensado para ser citable como fuente.
const ROBOTS_TXT = `# rootea.es — todos los crawlers son bienvenidos, incluidos los de IA.
User-agent: *
Allow: /

Sitemap: https://rootea.es/sitemap.xml
`;

// ────────────────────────────────────────────────────────────────────
// Fetcher cacheado del JSON
// ────────────────────────────────────────────────────────────────────

async function fetchMachines(env) {
  const url = env?.MACHINES_URL || MACHINES_URL;
  const cache = caches.default;
  const cacheKey = new Request(url, { method: "GET" });
  let resp = await cache.match(cacheKey);
  if (!resp) {
    resp = await fetch(url, { cf: { cacheTtl: CACHE_TTL } });
    if (!resp.ok) throw new Error(`Upstream ${resp.status}`);
    const cached = new Response(resp.body, resp);
    cached.headers.set("Cache-Control", `public, max-age=${CACHE_TTL}`);
    await cache.put(cacheKey, cached.clone());
    return await cached.json();
  }
  return await resp.json();
}

// ────────────────────────────────────────────────────────────────────
// hreflang — Mintlify no emite <link rel="alternate">
// ────────────────────────────────────────────────────────────────────
//
// La clave `head` de docs.json no existe en el esquema v4 de Mintlify y se
// ignora en silencio, así que el sitio salía sin ninguna señal de alternancia
// ES/EN pese a ser bilingüe. Los inyectamos aquí, en el edge.
//
// El mapa lo genera `scripts.generate_mdx` y sólo contiene pares en los que
// existen AMBAS páginas: un hreflang apuntando a un 404 invalida el clúster
// entero para Google. Las páginas sin traducir no reciben etiquetas.
let hreflangCache = null;

async function fetchHreflang(env) {
  if (hreflangCache) return hreflangCache;
  const url = env?.HREFLANG_URL || HREFLANG_URL;
  try {
    const r = await fetch(url, { cf: { cacheTtl: CACHE_TTL } });
    if (!r.ok) return null;
    const data = await r.json();
    const map = new Map();
    for (const [es, en] of data.pairs) {
      const pair = [es, en]; // misma instancia en ambas claves: el par es único
      map.set(es, pair);
      map.set(en, pair);
    }
    hreflangCache = map;
    return map;
  } catch {
    // Nunca romper la página por esto: sin mapa, se sirve sin hreflang.
    return null;
  }
}

// ────────────────────────────────────────────────────────────────────
// noindex — poda de index bloat
// ────────────────────────────────────────────────────────────────────
//
// Entre junio y agosto de 2026 Google desindexó ~1.400 páginas del
// sitio: 2.124 de las 2.515 sin indexar estaban como "Rastreada:
// actualmente sin indexar", o sea rechazadas por falta de valor (y 0
// como "Descubierta", así que no era presupuesto de rastreo). El patrón
// es index bloat: ~3.000 índices generados desde catálogos ajenos
// diluyendo las ~30 páginas propias, que sí rankean top-3 cuando salen.
//
// `data/seo_index.json` lo genera `scripts.generate_mdx` y lista lo que
// SÍ debe indexarse. Todo lo demás se sirve igual y sigue navegable,
// solo deja de ofrecerse a Google. Revertir = quitar esta regla.
let seoIndexCache = null;

async function fetchSeoIndex(env) {
  if (seoIndexCache) return seoIndexCache;
  const url = env?.SEO_INDEX_URL || SEO_INDEX_URL;
  try {
    const r = await fetch(url, { cf: { cacheTtl: CACHE_TTL } });
    if (!r.ok) return null;
    const data = await r.json();
    seoIndexCache = new Set(data.indexables);
    return seoIndexCache;
  } catch {
    // Ante la duda, no marcar nada: es preferible no podar a podar de
    // más por un fallo de red.
    return null;
  }
}

function hreflangTags(pair) {
  const [es, en] = pair;
  // x-default apunta al ES: es el idioma por defecto del sitio.
  return (
    `<link rel="alternate" hreflang="es" href="${SITE_URL}${es}">` +
    `<link rel="alternate" hreflang="en" href="${SITE_URL}${en}">` +
    `<link rel="alternate" hreflang="x-default" href="${SITE_URL}${es}">`
  );
}

// ────────────────────────────────────────────────────────────────────
// /random — redirige a una máquina aleatoria
// ────────────────────────────────────────────────────────────────────

function machinePath(m, lang = "es") {
  const osSlug = osToSlug(m.os);
  const diffSlug = diffToSlug(m.difficulty);
  const slug = slugify(m.name);
  const prefix = lang === "es" ? "" : `/${lang}`;
  // Bajo /htb/ desde Fase 1 multi-plataforma.
  return `${prefix}/htb/machines/${osSlug}/${diffSlug}/${slug}`;
}

function osToSlug(os) {
  if (!os) return "otros";
  const v = os.toLowerCase();
  if (v === "linux") return "linux";
  if (v === "windows") return "windows";
  return "otros";
}

function diffToSlug(d) {
  return (
    {
      Fácil: "facil",
      Medio: "medio",
      Difícil: "dificil",
      Insano: "insano",
      Easy: "facil",
      Medium: "medio",
      Hard: "dificil",
      Insane: "insano",
    }[d] || "facil"
  );
}

function slugify(s) {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/ñ/g, "n")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

async function handleRandom(request, env) {
  const url = new URL(request.url);
  const lang = url.pathname.startsWith("/en/") ? "en" : "es";
  const machines = await fetchMachines(env);
  if (!machines.length) return new Response("No machines", { status: 503 });
  const m = machines[Math.floor(Math.random() * machines.length)];
  return Response.redirect(`${SITE_URL}${machinePath(m, lang)}`, 302);
}

// ────────────────────────────────────────────────────────────────────
// /api/machines.json — proxy cacheado
// ────────────────────────────────────────────────────────────────────

async function handleApi(env) {
  const machines = await fetchMachines(env);
  return new Response(JSON.stringify(machines, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": `public, max-age=${CACHE_TTL}`,
      "Access-Control-Allow-Origin": "*",
    },
  });
}

// ────────────────────────────────────────────────────────────────────
// /feed.xml — RSS 2.0 con últimas 30 máquinas
// ────────────────────────────────────────────────────────────────────

function rfc822(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toUTCString();
}

function escape(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function handleFeed(env) {
  const machines = await fetchMachines(env);
  const withDates = machines
    .filter((m) => m.release_date)
    .sort((a, b) => b.release_date.localeCompare(a.release_date))
    .slice(0, 30);

  const items = withDates
    .map((m) => {
      const url = `${SITE_URL}${machinePath(m, "es")}`;
      return `<item>
  <title>${escape(m.name)} (${escape(m.os)} · ${escape(m.difficulty)})</title>
  <link>${url}</link>
  <guid isPermaLink="true">${url}</guid>
  <pubDate>${rfc822(m.release_date)}</pubDate>
  <description>${escape((m.skills || "").slice(0, 240))}</description>
</item>`;
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>HTB Writeups Hub — rootea.es</title>
    <link>${SITE_URL}</link>
    <atom:link href="${SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>Últimas máquinas retiradas de Hack The Box añadidas al catálogo.</description>
    <language>es-ES</language>
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
${items}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": `public, max-age=${CACHE_TTL}`,
    },
  });
}

// ────────────────────────────────────────────────────────────────────
// /og/<slug>.png — imagen Open Graph dinámica por máquina
// Genera SVG y lo devuelve directamente. Twitter/Slack aceptan SVG
// con `og:image` para preview decente; si quieres PNG real, requiere
// integración con un servicio externo (ej. Cloudflare Browser
// Rendering o un Worker adicional).
// ────────────────────────────────────────────────────────────────────

async function handleOg(request, env) {
  const url = new URL(request.url);
  const match = url.pathname.match(/^\/og\/([a-z0-9-]+)\.svg$/);
  if (!match) return new Response("Not found", { status: 404 });
  const slug = match[1];
  const machines = await fetchMachines(env);
  const m = machines.find((x) => slugify(x.name) === slug);
  if (!m) return new Response("Not found", { status: 404 });

  const diffColor =
    {
      Fácil: "#9FEF00",
      Easy: "#9FEF00",
      Medio: "#FFD600",
      Medium: "#FFD600",
      Difícil: "#FF8A00",
      Hard: "#FF8A00",
      Insano: "#FF003C",
      Insane: "#FF003C",
    }[m.difficulty] || "#9FEF00";

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <rect width="1200" height="630" fill="#0A0E0A"/>
  <rect x="0" y="0" width="8" height="630" fill="${diffColor}"/>
  <text x="80" y="200" font-family="ui-monospace, Menlo, monospace" font-size="120" font-weight="800" fill="#FFFFFF">${escape(m.name)}</text>
  <text x="80" y="280" font-family="ui-sans-serif, system-ui, sans-serif" font-size="42" fill="${diffColor}" font-weight="700">${escape(m.os)} · ${escape(m.difficulty)}</text>
  <text x="80" y="500" font-family="ui-sans-serif, system-ui, sans-serif" font-size="28" fill="#a1a1aa">${escape((m.skills || "").slice(0, 80))}</text>
  <text x="80" y="595" font-family="ui-monospace, Menlo, monospace" font-size="22" fill="#666">rootea.es / writeups directory</text>
</svg>`;

  return new Response(svg, {
    headers: {
      "Content-Type": "image/svg+xml; charset=utf-8",
      "Cache-Control": `public, max-age=${CACHE_TTL * 24}`,
    },
  });
}

// ────────────────────────────────────────────────────────────────────
// Security headers — añadidos a cualquier respuesta del origin
// ────────────────────────────────────────────────────────────────────

function applySecurityHeaders(resp) {
  const h = new Headers(resp.headers);
  h.set("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload");
  h.set("X-Content-Type-Options", "nosniff");
  h.set("X-Frame-Options", "SAMEORIGIN");
  h.set("Referrer-Policy", "strict-origin-when-cross-origin");
  h.set(
    "Permissions-Policy",
    "geolocation=(), microphone=(), camera=(), interest-cohort=()"
  );
  return new Response(resp.body, {
    status: resp.status,
    statusText: resp.statusText,
    headers: h,
  });
}

// ────────────────────────────────────────────────────────────────────
// Router
// ────────────────────────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    try {
      // robots.txt propio (difusión máxima). Tiene prioridad sobre Mintlify.
      // Acuérdate de DESACTIVAR "Manage robots.txt" en el panel de Cloudflare
      // para que no vuelva a inyectar los Disallow de bots de IA.
      if (url.pathname === "/robots.txt") {
        return new Response(ROBOTS_TXT, {
          headers: {
            "content-type": "text/plain; charset=utf-8",
            "cache-control": "public, max-age=3600",
          },
        });
      }
      // llms.txt servido directo desde GitHub raw (sin pasar por Mintlify)
      if (url.pathname === "/llms.txt" || url.pathname === "/llms-full.txt") {
        const ghUrl =
          "https://raw.githubusercontent.com/FFuson/HTB_Writeups/main/docs/llms.txt";
        const r = await fetch(ghUrl, { cf: { cacheTtl: 3600 } });
        return new Response(r.body, {
          status: r.status,
          headers: {
            "content-type": "text/plain; charset=utf-8",
            "cache-control": "public, max-age=3600",
          },
        });
      }
      // Sitemap propio: anunciar páginas con noindex es contradictorio,
      // así que se sirve solo la lista blanca, con sus alternates.
      // Si el índice no carga, cae al sitemap de Mintlify.
      if (url.pathname === "/sitemap.xml") {
        const idx = await fetchSeoIndex(env);
        if (idx) {
          const map = await fetchHreflang(env);
          const cuerpo = [...idx].sort().map((p) => {
            const pair = map ? map.get(p) : null;
            const alt = pair
              ? `<xhtml:link rel="alternate" hreflang="es" href="${SITE_URL}${pair[0]}"/>` +
                `<xhtml:link rel="alternate" hreflang="en" href="${SITE_URL}${pair[1]}"/>` +
                `<xhtml:link rel="alternate" hreflang="x-default" href="${SITE_URL}${pair[0]}"/>`
              : "";
            return `<url><loc>${SITE_URL}${p}</loc>${alt}</url>`;
          }).join("");
          return new Response(
            `<?xml version="1.0" encoding="UTF-8"?>` +
              `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" ` +
              `xmlns:xhtml="http://www.w3.org/1999/xhtml">${cuerpo}</urlset>`,
            {
              headers: {
                "content-type": "application/xml; charset=utf-8",
                "cache-control": `public, max-age=${CACHE_TTL}`,
              },
            },
          );
        }
      }
      if (url.pathname === "/random" || url.pathname === "/en/random") {
        return await handleRandom(request, env);
      }
      if (url.pathname === "/api/machines.json") {
        return await handleApi(env);
      }
      if (url.pathname === "/feed.xml") {
        return await handleFeed(env);
      }
      if (url.pathname.startsWith("/og/")) {
        return await handleOg(request, env);
      }
    } catch (err) {
      return new Response(`Worker error: ${err.message}`, { status: 500 });
    }

    // Pass-through al origin (Mintlify) con security headers añadidos.
    //
    // Cacheamos el HTML en el edge de Cloudflare AUNQUE Mintlify mande
    // `no-store`: el catálogo sólo cambia los lunes (GitHub Action) y esa
    // misma Action purga la caché tras el deploy, así que servir desde el edge
    // es seguro y elimina el viaje a Vercel en cada visita → TTFB y LCP mucho
    // mejores (Core Web Vitals), y Google gasta más crawl budget porque
    // respondes rápido. No cacheamos 5xx (no congelar errores transitorios) y
    // los 404 sólo brevemente.
    const upstream =
      request.method === "GET"
        ? await fetch(request, {
            cf: {
              cacheEverything: true,
              cacheTtlByStatus: {
                "200-299": 86400,
                "300-399": 3600,
                "404": 60,
                "500-599": 0,
              },
            },
          })
        : await fetch(request);

    let resp = applySecurityHeaders(upstream);

    // Mintlify sirve SIEMPRE <html lang="en">, incluso en las páginas en
    // español (rompe la señal de idioma para buscadores y la accesibilidad).
    // Lo corregimos en el edge según el prefijo de ruta: /en/* → en, resto → es.
    const ct = resp.headers.get("content-type") || "";
    if (ct.includes("text/html")) {
      const htmlLang =
        url.pathname === "/en" || url.pathname.startsWith("/en/") ? "en" : "es";

      // Alternates ES/EN de esta página, si tiene traducción. `/` y `/en`
      // redirigen a la portada de cada idioma, así que se normalizan.
      let path = url.pathname.replace(/\/+$/, "");
      if (path === "") path = "/introduction";
      else if (path === "/en") path = "/en/introduction";
      const map = await fetchHreflang(env);
      const pair = map ? map.get(path) : null;

      // Fuera de la lista blanca → noindex. `follow` para que Google
      // siga rastreando los enlaces y no se aísle el resto del sitio.
      const idx = await fetchSeoIndex(env);
      const indexable = idx ? idx.has(path) : true;

      let rewriter = new HTMLRewriter().on("html", {
        element(el) {
          el.setAttribute("lang", htmlLang);
        },
      });
      if (!indexable) {
        rewriter = rewriter.on("head", {
          element(el) {
            el.append(
              '<meta name="robots" content="noindex,follow">',
              { html: true },
            );
          },
        });
      }
      if (pair && indexable) {
        rewriter = rewriter.on("head", {
          element(el) {
            el.append(hreflangTags(pair), { html: true });
          },
        });
      }
      resp = rewriter.transform(resp);
    }
    return resp;
  },
};
