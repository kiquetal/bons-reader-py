# BVA Emissions Scraper — Agent Context

## Wing: `bva-emisiones`

### Room: project-overview

This project scrapes bond emissions from the Bolsa de Valores de Asunción (BVA), Paraguay's stock exchange.
Source: https://www.bolsadevalores.com.py/nuevas-emisiones/

It runs weekly (Wednesdays ~12:00 UTC) via GitHub Actions, or locally with `python scraper.py`.

### Room: data-schema

Each JSON entry in `data/emisiones.json` represents a single bond series with these fields:

- `name` — Issuer name (e.g. "BANCO FAMILIAR S.A.E.C.A.")
- `instrument` — Type, usually "bono"
- `qualification` — Risk rating (e.g. "AApy Estable.")
- `percentage` — Annual interest rate as string (e.g. "5,65%"). Uses comma as decimal separator
- `date` — Emission date in Spanish (e.g. "Jue, abril 23, 2026")
- `duration` — Term in days as integer (e.g. 732)
- `isin` — ISIN code (e.g. "PYFAM03F0006")
- `agente_colocador` — Placement agent / broker
- `series_count` — How many series the parent emission has (one emission can have multiple series)
- `url` — Detail page URL on BVA website

### Room: query-guide

When answering questions about this data:

- Interest rates use comma as decimal separator (e.g. "5,65%" means 5.65%)
- Duration is always in days. Divide by 365 for approximate years
- Bonds with interest rate > 11% are considered high-yield and flagged in alerts
- One emission (issuer + date) can have multiple series, each with its own ISIN, rate, and duration
- `qualification` follows Paraguayan risk rating scale (AApy, Apy, BBBpy, etc.). "Estable" means stable outlook
- Dates are in Spanish: Lun=Mon, Mar=Tue, Mié=Wed, Jue=Thu, Vie=Fri, Sáb=Sat, Dom=Sun
- Common issuers include banks (Banco Familiar, Banco Continental, Sudameris), financieras, and cooperatives

### Room: execution-log

Last execution: check `data/emisiones.json` modification date for the most recent scrape.
Schedule: every Wednesday at 12:00 UTC (~08:00 PYT).
Output location: `data/emisiones.json`

### Room: useful-queries

Example questions this data can answer:

- What bonds have the highest interest rate right now?
- Which issuers have emissions with more than 2 years duration?
- Show me all bonds from Banco Familiar
- What's the average interest rate across current emissions?
- Which bonds are rated below AApy?
- List all high-yield bonds (>11% interest)
- What placement agents are most active?
- Compare short-term vs long-term bond rates
