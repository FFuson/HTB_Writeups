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

const SITE_URL = "https://rootea.es";
const CACHE_TTL = 60 * 60; // 1h

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
// /random — redirige a una máquina aleatoria
// ────────────────────────────────────────────────────────────────────

function machinePath(m, lang = "es") {
  const osSlug = osToSlug(m.os);
  const diffSlug = diffToSlug(m.difficulty);
  const slug = slugify(m.name);
  const prefix = lang === "es" ? "" : `/${lang}`;
  return `${prefix}/machines/${osSlug}/${diffSlug}/${slug}`;
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

    // Pass-through al origin con security headers añadidos
    const upstream = await fetch(request);
    return applySecurityHeaders(upstream);
  },
};
