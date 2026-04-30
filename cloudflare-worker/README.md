# Cloudflare Worker — rootea.es

Worker que añade endpoints dinámicos a la web sin romper el resto.

## Endpoints

| Ruta | Qué hace |
|---|---|
| `/random` | Redirige (302) a una máquina aleatoria del catálogo. |
| `/en/random` | Idem, devuelve URL en `/en/`. |
| `/api/machines.json` | API JSON cacheada (1h) con todo el catálogo. |
| `/feed.xml` | RSS 2.0 con las últimas 30 máquinas. |
| `/og/<slug>.svg` | Open Graph dinámica por máquina. |
| Resto | Pass-through al origin Mintlify, con headers de seguridad añadidos. |

## Deploy desde el panel de Cloudflare (sin CLI)

1. Cloudflare Dashboard → Workers & Pages → **Create application** →
   **Create Worker** → asigna nombre `rootea-worker`.
2. **Edit code** → pega el contenido de `worker.js` → **Deploy**.
3. **Settings** → **Triggers** → **Add Custom Domain**: añade
   `rootea.es` (debe estar en tu zona DNS de CF).
   - Alternativa con Routes: añade `rootea.es/*` apuntando al
     worker, dejando `*.mintlify.app` fuera.
4. **Settings** → **Variables** → añade
   `MACHINES_URL` con el valor del raw GitHub URL.

## Deploy con Wrangler (CLI)

Requiere [Wrangler](https://developers.cloudflare.com/workers/wrangler/install-and-update/):

```bash
npm install -g wrangler
cd cloudflare-worker
wrangler login
# Descomenta la sección [[routes]] en wrangler.toml con tu zona
wrangler deploy
```

## Iteración local

```bash
wrangler dev
# expone el worker en http://localhost:8787
```

Prueba:

```bash
curl -I http://localhost:8787/random
curl    http://localhost:8787/api/machines.json | jq '. | length'
curl    http://localhost:8787/feed.xml | head -20
curl    http://localhost:8787/og/lame.svg | head
```

## Coste

**Free tier de Cloudflare**: 100.000 invocaciones/día. Cero coste
para este uso.

## Notas

- El `og/.svg` devuelve SVG. Twitter, Slack y LinkedIn aceptan SVG
  como `og:image` razonablemente bien. Si necesitas PNG real,
  integrar [Cloudflare Browser Rendering](https://developers.cloudflare.com/browser-rendering/)
  o [Satori](https://github.com/vercel/satori) en otro Worker.
- Los **security headers** se aplican a cualquier respuesta del
  origin, no sólo a las rutas custom.
- El cache TTL es 1h. Una nueva regeneración del catálogo (lunes
  06:00 UTC) tarda hasta 1h en propagarse a `/api/machines.json` y
  `/feed.xml`. Si quieres forzar refresh, usa el botón "Purge cache"
  del panel CF.
