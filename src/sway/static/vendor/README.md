# Vendored browser dependency

- HTMX 2.0.10: https://github.com/bigskysoftware/htmx/releases/tag/v2.0.10
- Distribution: https://raw.githubusercontent.com/bigskysoftware/htmx/v2.0.10/dist/htmx.min.js
- License: `HTMX-LICENSE` (BSD 2-Clause)

Serving the pinned distribution locally keeps gameplay independent of external CDNs. Update the versioned filename, page reference and license together in a reviewed PR. The application uses HTMX only for submitted decisions and bounded bot progress; selection and ordering run in `app.js`.
