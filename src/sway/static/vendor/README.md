# Vendored browser dependency

- HTMX 2.0.8: https://github.com/bigskysoftware/htmx/releases/tag/v2.0.8
- Distribution: https://unpkg.com/htmx.org@2.0.8/dist/htmx.min.js
- License: `HTMX-LICENSE` (BSD 2-Clause)

Serving the pinned distribution locally keeps gameplay independent of external CDNs. Update the versioned filename, page reference and license together in a reviewed PR. The application uses HTMX only for submitted decisions and bounded bot progress; selection and ordering run in `app.js`.
