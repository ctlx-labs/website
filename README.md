# website

The public website for ctlx.holdings, served by GitHub Pages from `main` (root). ctlx.me forwards to it.

- `index.html`: the one page. Plain HTML and CSS, no build step, no external fonts or scripts.
- `CNAME`: the custom domain for GitHub Pages.

Design: Catalyx brand as used in `chad-2030-simulator` (burgundy `#C1272D`, gold `#D4961F`, Arial; wordmark with the X above the name).
Voice: the deal kit's `mandate/voice.yaml` rules (no selling, no contrast framing, figures over adjectives).

DNS (Squarespace DNS): only the web records point here (apex A records to GitHub Pages, `www` CNAME to `ctlx-labs.github.io`).
The MX, SPF and MS= verification records for Microsoft 365 mail are not touched.
