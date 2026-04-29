> 🇪🇸 Español (abajo) · 🇬🇧 [Read in English ↓](#security-policy-english)

# Política de Seguridad

## Reportar una vulnerabilidad

Si crees haber encontrado un problema de seguridad en este
repositorio (no en el contenido enlazado, sino en el código del
agregador o en el sitio publicado), por favor:

1. **NO** abras un issue público.
2. Usa el canal privado de GitHub:
   <https://github.com/FFuson/HTB_Writeups/security/advisories/new>
   (botón "Report a vulnerability").
3. Espera respuesta antes de divulgar nada públicamente.

## Alcance

En alcance:

- El código Python del pipeline (`scripts/`).
- La GitHub Action (`.github/workflows/`).
- El sitio publicado (`rootea.es`) — específicamente XSS o
  data-leak provocados por nuestro código de generación.

Fuera de alcance:

- Vulnerabilidades en Mintlify (reportar a
  <https://mintlify.com/security>).
- Vulnerabilidades en GitHub o GitHub Actions
  (reportar a <https://bounty.github.com/>).
- Reportes de DMCA o solicitudes de retirada de contenido enlazado
  (usar issue público con etiqueta `legal`).

## Política de divulgación

Tras confirmar el reporte, fijaremos una fecha de divulgación
coordinada (típicamente 14-30 días tras el fix). Se acreditará al
investigador en el changelog si así lo desea.

---
---

<a id="security-policy-english"></a>

> 🇬🇧 English · 🇪🇸 [Leer en español ↑](#política-de-seguridad)

# Security Policy

## Reporting a vulnerability

If you believe you've found a security issue in this repository
(not in the linked content, but in the aggregator code or the
published site), please:

1. **DO NOT** open a public issue.
2. Use GitHub's private channel:
   <https://github.com/FFuson/HTB_Writeups/security/advisories/new>
   ("Report a vulnerability" button).
3. Wait for a response before disclosing anything publicly.

## Scope

In scope:

- Python pipeline code (`scripts/`).
- The GitHub Action (`.github/workflows/`).
- The published site (`rootea.es`) — specifically XSS or data leaks
  caused by our generation code.

Out of scope:

- Vulnerabilities in Mintlify (report to
  <https://mintlify.com/security>).
- Vulnerabilities in GitHub or GitHub Actions (report to
  <https://bounty.github.com/>).
- DMCA reports or content takedown requests (use a public issue
  tagged `legal`).

## Disclosure policy

After confirming the report, we'll set a coordinated disclosure
date (typically 14-30 days after the fix). The researcher will be
credited in the changelog if they wish.
