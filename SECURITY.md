# Security Policy

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
