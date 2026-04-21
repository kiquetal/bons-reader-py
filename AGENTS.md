# BVA Emissions Scraper — Agent Context

## Wing: `bva-emisiones`

### Room: investment-offers

Contains bond emissions scraped from https://www.bolsadevalores.com.py/nuevas-emisiones/
Each entry in `data/emisiones.json` is a single bond series with: issuer name, instrument type, risk rating, interest rate, emission date, term in days, ISIN code, and placement agent.
One emission can have multiple series, each with its own rate and duration.

### Room: yield-rates

Interest rates use comma as decimal separator (e.g. "5,65%" = 5.65%).
Bonds with rate > 11% are flagged as high-yield.
Duration is in days — divide by 365 for years.

### Room: risk-ratings

Ratings follow the Paraguayan scale: AApy, Apy, BBBpy, etc.
"Estable" means stable outlook.
Common issuers: banks (Banco Familiar, Banco Continental, Sudameris), financieras, and cooperatives.

### Room: schedule

Scraper runs every Tuesday and Thursday at 12:00 UTC (~08:00 PYT).
Output: `data/emisiones.json`. Check its modification date for last execution.
Dates in the data are in Spanish: Lun, Mar, Mié, Jue, Vie, Sáb, Dom.

### Room: finished-tasks

- Updated scraper schedule from Wednesday to Tuesday and Thursday (cron: `0 12 * * 2,4`).
- Added `environment` to the scraper GitHub Actions workflow.
- Included date in the email subject for better traceability.
