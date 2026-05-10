<div align="center">

# rootea.es · Writeups HackTheBox · PortSwigger · TryHackMe

🇪🇸 Español (abajo) · 🇬🇧 [Read in English ↓](#english)

**Directorio bilingüe ES/EN de writeups verificados de HackTheBox,
PortSwigger Web Security Academy y TryHackMe.** Enlaces validados
semanalmente. Cero contenido propio: sólo enlaces a los autores
originales.

[![Site](https://img.shields.io/website?url=https%3A%2F%2Frootea.es&label=rootea.es&up_color=9FEF00)](https://rootea.es)
[![Refresh](https://github.com/FFuson/HTB_Writeups/actions/workflows/refresh.yml/badge.svg)](https://github.com/FFuson/HTB_Writeups/actions/workflows/refresh.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-9FEF00.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

🌐 **[rootea.es](https://rootea.es)** · 🇪🇸 [Español](https://rootea.es) · 🇬🇧 [English](https://rootea.es/en)

</div>

---

## Qué es

Un único lugar donde encontrar writeups de calidad para máquinas
**retiradas** de HackTheBox, **labs** de PortSwigger Web Security
Academy y **rooms** públicas de TryHackMe. La documentación está
dispersa entre cientos de blogs, canales de YouTube y posts
efímeros — este hub resuelve la fragmentación en las tres plataformas.

- 🎯 **1.454 retos indexados** entre las tres plataformas
  (203 máquinas HackTheBox + 262 labs PortSwigger + 989 rooms
  TryHackMe).
- 🔗 **2.280 writeups validados** vía `HEAD` requests cada semana.
- 🧠 **1.444 recursos por skill** mapeados a HackTricks, GTFOBins,
  PortSwigger Academy y otros.
- 🌐 **Bilingüe** (español por defecto, inglés disponible en `/en/`).
- ⚖️ **Respeta los términos de cada plataforma**: sólo máquinas
  retiradas de HackTheBox, labs públicos de PortSwigger y rooms
  gratuitos de TryHackMe.

## Autores en lista blanca

Sólo se indexan writeups de los siguientes autores, elegidos por
calidad consistente en cada plataforma:

### HackTheBox

| Autor | Idioma | Formato |
|---|---|---|
| [S4vitar](https://www.youtube.com/@s4vitar) | 🇪🇸 ES | Vídeo |
| [El Pingüino de Mario](https://www.youtube.com/@elpinguinodemario) | 🇪🇸 ES | Vídeo |
| [0xdf](https://0xdf.gitlab.io) | 🇬🇧 EN | Texto |
| [IppSec](https://ippsec.rocks) | 🇬🇧 EN | Vídeo |

### PortSwigger Web Security Academy

| Autor | Idioma | Formato |
|---|---|---|
| [PortSwigger oficial](https://portswigger.net/web-security) | 🇬🇧 EN | Texto |
| [Rana Khalil](https://www.youtube.com/@RanaKhalil101) | 🇬🇧 EN | Vídeo |
| [z3nsh3ll](https://www.youtube.com/@z3nsh3ll) | 🇬🇧 EN | Vídeo |

### TryHackMe

| Autor | Idioma | Formato |
|---|---|---|
| [TryHackMe oficial](https://tryhackme.com) | 🇬🇧 EN | Texto |
| [JohnHammond](https://www.youtube.com/@_JohnHammond) | 🇬🇧 EN | Vídeo |
| [stuffy24](https://www.youtube.com/@stuffy24) | 🇬🇧 EN | Vídeo |

## Cómo se usa

Vete a **[rootea.es](https://rootea.es)** y:

- **Pestañas superiores** — HackTheBox, PortSwigger, TryHackMe y
  Skills.
- **Tabla maestra por plataforma** —
  [HackTheBox](https://rootea.es/htb/all),
  [PortSwigger](https://rootea.es/portswigger/all),
  [TryHackMe](https://rootea.es/tryhackme/all). Vista única con
  charts y filtros visuales.
- **Buscador** — `Cmd+K` (o `Ctrl+K`). Indexa nombres, labs, rooms
  y skills.
- **Roadmap OSCP** — selección curada de 30 máquinas de HackTheBox
  para preparar el examen.
- **Recién retiradas** — [/htb/recientes](https://rootea.es/htb/recientes)
  con las últimas máquinas que han salido del ranking activo.
- **Máquina aleatoria** — [/random](https://rootea.es/random) te
  lleva a una máquina HackTheBox al azar (vía Cloudflare Worker).
- **RSS** — suscríbete al [feed](https://rootea.es/feed.xml) para
  enterarte de las nuevas máquinas indexadas.
- **API JSON** — el catálogo HackTheBox se sirve en
  [`/api/machines.json`](https://rootea.es/api/machines.json) para
  reutilizarlo en herramientas propias.

## Más allá del agregador

rootea.es no es sólo writeups. Las plataformas (HackTheBox,
TryHackMe, PortSwigger, OffSec) entrenan operadores; **no entrenan
auditores profesionales**. Por eso el sitio incluye:

- **[Glosario táctico](https://rootea.es/glosario)** — 100+ términos
  de pentest con formato fijo: trinchera, kill chain, huella
  defensiva, falso amigo, remediación.
- **[Metodología profesional](https://rootea.es/metodologia)** —
  fases PTES, árboles de decisión SMB/AD/Web, regla del cronómetro,
  exploit chaining, MITRE ATT&CK.
- **[Plantilla de informe](https://rootea.es/plantilla-informe)** —
  las 4 páginas que pagan al consultor: ejecutivo, técnico,
  escalada, remediación.
- **Especialización avanzada** — [AD CS · Certipy](https://rootea.es/ad-cs),
  [Cloud Pentest](https://rootea.es/cloud-pentest),
  [LLM Security](https://rootea.es/llm-security),
  [Red Team moderno](https://rootea.es/red-team-moderno),
  [Bug Bounty + CVE](https://rootea.es/bug-bounty).

## Cómo se actualiza

El catálogo se regenera **automáticamente cada lunes** desde una
GitHub Action: re-detecta máquinas/labs/rooms nuevas, valida que
los enlaces sigan vivos sobre las tres plataformas, y actualiza el
sitio sin intervención manual.

## Cómo contribuir

Bienvenidas tres formas de contribución, cada una con su plantilla
de issue:

- 🔗 [Reportar enlace muerto](https://github.com/FFuson/HTB_Writeups/issues/new?template=dead-link.yml)
- ✍️ [Proponer un autor nuevo](https://github.com/FFuson/HTB_Writeups/issues/new?template=new-author.yml)
- 🛠 [Añadir una skill al glosario](https://github.com/FFuson/HTB_Writeups/issues/new?template=new-skill.yml)

Si vas a abrir un Pull Request, lee primero
[CONTRIBUTING.md](CONTRIBUTING.md).

## Aviso legal

HackTheBox, PortSwigger y TryHackMe son marcas registradas de sus
respectivos titulares. Este proyecto **no está afiliado** a ninguna
de las plataformas ni a los autores listados. Sólo enlaza al
material que ellos han publicado abiertamente.

Si eres uno de los autores y deseas que tu material no aparezca
listado, abre un [issue con etiqueta `legal`](https://github.com/FFuson/HTB_Writeups/issues/new?labels=legal)
y será retirado al día siguiente.

## Seguridad

Para reportar vulnerabilidades de seguridad **del código o del
sitio** (no del contenido enlazado), consulta
[SECURITY.md](SECURITY.md).

## Licencia

[MIT](LICENSE) — el código se libera para que cualquiera pueda
montar su propio agregador.

---

<div align="center">

**¿Te ha sido útil?** Da una ⭐ y, sobre todo, suscríbete a los
canales de los autores originales — sin ellos no hay catálogo.

</div>

---
---

<a id="english"></a>

<div align="center">

# rootea.es · Writeups HackTheBox · PortSwigger · TryHackMe

🇬🇧 English · 🇪🇸 [Leer en español ↑](#rooteaes--writeups-hackthebox--portswigger--tryhackme)

**Bilingual ES/EN directory of verified writeups for HackTheBox,
PortSwigger Web Security Academy and TryHackMe.** Links validated
weekly. Zero own content: just links to the original authors.

</div>

---

## What it is

A single place to find quality writeups for **retired** HackTheBox
machines, PortSwigger Web Security Academy **labs**, and public
TryHackMe **rooms**. Documentation is scattered across hundreds of
blogs, YouTube channels, and ephemeral Medium posts — this hub
solves the fragmentation across all three platforms.

- 🎯 **1,454 indexed challenges** across the three platforms
  (203 HackTheBox machines + 262 PortSwigger labs + 989 TryHackMe
  rooms).
- 🔗 **2,280 validated writeups** via weekly `HEAD` requests.
- 🧠 **1,444 skill resources** mapped to HackTricks, GTFOBins,
  PortSwigger Academy, and others.
- 🌐 **Bilingual** (Spanish by default, English at `/en/`).
- ⚖️ **Respects each platform's terms**: only retired HackTheBox
  machines, public PortSwigger labs, and free TryHackMe rooms.

## Whitelisted authors

Only writeups from the following authors are indexed, chosen for
consistent quality on each platform:

### HackTheBox

| Author | Language | Format |
|---|---|---|
| [S4vitar](https://www.youtube.com/@s4vitar) | 🇪🇸 ES | Video |
| [El Pingüino de Mario](https://www.youtube.com/@elpinguinodemario) | 🇪🇸 ES | Video |
| [0xdf](https://0xdf.gitlab.io) | 🇬🇧 EN | Text |
| [IppSec](https://ippsec.rocks) | 🇬🇧 EN | Video |

### PortSwigger Web Security Academy

| Author | Language | Format |
|---|---|---|
| [PortSwigger official](https://portswigger.net/web-security) | 🇬🇧 EN | Text |
| [Rana Khalil](https://www.youtube.com/@RanaKhalil101) | 🇬🇧 EN | Video |
| [z3nsh3ll](https://www.youtube.com/@z3nsh3ll) | 🇬🇧 EN | Video |

### TryHackMe

| Author | Language | Format |
|---|---|---|
| [TryHackMe official](https://tryhackme.com) | 🇬🇧 EN | Text |
| [JohnHammond](https://www.youtube.com/@_JohnHammond) | 🇬🇧 EN | Video |
| [stuffy24](https://www.youtube.com/@stuffy24) | 🇬🇧 EN | Video |

## How to use it

Head to **[rootea.es/en](https://rootea.es/en)** and:

- **Top tabs** — HackTheBox, PortSwigger, TryHackMe and Skills.
- **Master table per platform** —
  [HackTheBox](https://rootea.es/en/htb/all),
  [PortSwigger](https://rootea.es/en/portswigger/all),
  [TryHackMe](https://rootea.es/en/tryhackme/all). Single view with
  charts and visual filters.
- **Search** — `Cmd+K` (or `Ctrl+K`). Indexes names, labs, rooms
  and skills.
- **OSCP roadmap** — curated selection of 30 HackTheBox machines
  for exam prep.
- **Recently retired** — [/en/htb/recently-retired](https://rootea.es/en/htb/recently-retired)
  with the latest machines that left the active ranking.
- **Random machine** — [/en/random](https://rootea.es/en/random)
  takes you to a random HackTheBox machine (via Cloudflare Worker).
- **RSS** — subscribe to the [feed](https://rootea.es/feed.xml) to
  catch new machines as they get indexed.
- **JSON API** — the HackTheBox catalog is served at
  [`/api/machines.json`](https://rootea.es/api/machines.json) for
  reuse in your own tools.

## Beyond the aggregator

rootea.es is not just writeups. Training platforms (HackTheBox,
TryHackMe, PortSwigger, OffSec) produce operators; **they don't
produce professional auditors**. The site also includes:

- **[Tactical glossary](https://rootea.es/en/glossary)** — 100+
  pentest terms with a fixed format: trench, kill chain, defensive
  footprint, false friend, remediation.
- **[Professional methodology](https://rootea.es/en/methodology)** —
  PTES phases, SMB/AD/Web decision trees, the stopwatch rule,
  exploit chaining, MITRE ATT&CK.
- **[Report template](https://rootea.es/en/report-template)** — the
  4 pages that pay the consultant: executive, technical, escalation,
  remediation.
- **Advanced specialization** — [AD CS · Certipy](https://rootea.es/en/ad-cs),
  [Cloud Pentest](https://rootea.es/en/cloud-pentest),
  [LLM Security](https://rootea.es/en/llm-security),
  [Modern Red Team](https://rootea.es/en/modern-red-team),
  [Bug Bounty + CVE](https://rootea.es/en/bug-bounty).

## How it stays up to date

The catalog regenerates **automatically every Monday** via a
GitHub Action: it re-detects new machines/labs/rooms, validates
that links still resolve across all three platforms, and updates
the site without manual intervention.

## How to contribute

Three contribution paths are welcome, each with an issue template:

- 🔗 [Report a dead link](https://github.com/FFuson/HTB_Writeups/issues/new?template=dead-link.yml)
- ✍️ [Propose a new author](https://github.com/FFuson/HTB_Writeups/issues/new?template=new-author.yml)
- 🛠 [Add a skill to the glossary](https://github.com/FFuson/HTB_Writeups/issues/new?template=new-skill.yml)

If you're opening a Pull Request, read [CONTRIBUTING.md](CONTRIBUTING.md)
first.

## Legal

HackTheBox, PortSwigger and TryHackMe are registered trademarks of
their respective owners. This project is **not affiliated** with
any of the platforms nor with any of the listed authors. It only
links to material they have publicly published.

If you are one of the authors and wish your material to be removed
from the listing, open an [issue tagged `legal`](https://github.com/FFuson/HTB_Writeups/issues/new?labels=legal)
and it will be taken down the next day.

## Security

To report security vulnerabilities **in the code or the site**
(not in linked content), see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) — the code is released so anyone can run their own
aggregator.

---

<div align="center">

**Found it useful?** Drop a ⭐ and, more importantly, subscribe to
the original authors' channels — without them there's no catalog.

</div>
