import argparse
from datetime import datetime, timezone
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE = "https://www.bolsadevalores.com.py"
LISTING_URL = f"{BASE}/nuevas-emisiones/"
AJAX_URL = f"{BASE}/wp-admin/admin-ajax.php"
INTEREST_THRESHOLD = 11.0
MEMPALACE_BIN = shutil.which("mempalace")


def get_detail_urls(n=30):
    """Scrape listing page + AJAX load-more to collect up to n detail URLs."""
    resp = requests.get(LISTING_URL, timeout=30)
    resp.raise_for_status()
    html = resp.text

    urls = re.findall(
        r'data-url="(https://www\.bolsadevalores\.com\.py/nuevas-emisiones/[^"]+)"',
        html,
    )
    seen = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))]

    # Signature is HTML-entity-encoded in data-nav JSON
    sig_match = re.search(r'&quot;signature&quot;:&quot;([a-f0-9]+)&quot;', html)
    qid_match = re.search(r'data-queried-id="([^"]+)"', html)
    if not sig_match or not qid_match:
        return urls[:n]

    signature = sig_match.group(1)
    queried_id = qid_match.group(1)

    # Load more pages via AJAX until we have enough
    page = 2
    while len(urls) < n:
        data = {
            "action": "jet_engine_ajax",
            "handler": "listing_load_more",
            "page": str(page),
            "listing_id": "323",
            "queried_id": queried_id,
            "query[post_status][0]": "publish",
            "query[post_type]": "emisiones",
            "query[posts_per_page]": "12",
            "query[paged]": "1",
            "query[ignore_sticky_posts]": "1",
            "query[order]": "DESC",
            "query[orderby]": "meta_value",
            "query[meta_key]": "fecha-de-emision",
            "query[suppress_filters]": "false",
            "query[jet_smart_filters]": "jet-engine/default",
            "query[signature]": signature,
            "widget_settings[lisitng_id]": "323",
            "widget_settings[posts_num]": "10",
            "widget_settings[columns]": "4",
            "widget_settings[use_load_more]": "yes",
            "widget_settings[load_more_id]": "loadmore",
            "widget_settings[load_more_type]": "click",
        }
        r = requests.post(AJAX_URL, data=data, timeout=30)
        body = r.json()
        if not body.get("success"):
            break
        new = re.findall(
            r'data-url="(https://www\.bolsadevalores\.com\.py/nuevas-emisiones/[^"]+)"',
            body["data"]["html"],
        )
        if not new:
            break
        for u in new:
            if u not in seen:
                seen.add(u)
                urls.append(u)
        page += 1

    return urls[:n]


def parse_percentage(text):
    """Extract numeric percentage from text like '5,65%' or '12.35%'."""
    m = re.search(r"([\d.,]+)\s*%", text)
    if not m:
        return 0.0
    return float(m.group(1).replace(".", "").replace(",", "."))


def parse_duration(text):
    """Extract numeric duration (days) from text like '1.097' or '732'."""
    cleaned = text.strip().replace(".", "").replace(",", "")
    m = re.search(r"\d+", cleaned)
    return int(m.group()) if m else 0


def parse_emission(url):
    """Fetch a detail page and return a list of dicts, one per series."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Build h2 label->value map: value is the next element's text
    h2_map = {}
    name = ""
    found_datos = False
    for h2 in soup.find_all("h2"):
        txt = h2.get_text(strip=True)
        if txt == "Datos del Emisor":
            found_datos = True
            continue
        if found_datos and not name:
            name = txt
            continue
        nxt = h2.find_next()
        if nxt and nxt != h2:
            h2_map[txt.lower()] = nxt.get_text(strip=True)

    instrument = h2_map.get("instrumento", "")
    qualification = h2_map.get("calificación de riesgo", "")
    date_raw = h2_map.get("fecha de emisión", "")

    # Parse series from h3 headers
    series_data = []
    current = {}
    for h3 in soup.find_all("h3"):
        label = h3.get_text(strip=True).lower()
        nxt = h3.find_next()
        val = nxt.get_text(strip=True) if nxt else ""

        if "número de serie" in label:
            if current:
                series_data.append(current)
            current = {}
        elif "código isin" in label:
            current["isin"] = val
        elif "tasa de interés" in label:
            current["percentage"] = val
        elif "plazo de vencimiento" in label:
            current["duration"] = val
        elif "observación" in label:
            nxt_sib = h3.find_next_sibling()
            obs = nxt_sib.get_text(strip=True) if nxt_sib else ""
            m = re.search(
                r"(?:Agente\s+(?:de\s+)?Colocaci[oó]n|(?:Agente|Intermediario)\s+Colocador)[:\s]*(.+?)(?:Calificación|Destino|$)",
                obs, re.IGNORECASE,
            )
            current["agente_colocador"] = m.group(1).strip().rstrip(".") if m else ""

    if current:
        series_data.append(current)

    series_count = len(series_data)

    if not series_data:
        return [{
            "name": name, "instrument": instrument, "qualification": qualification,
            "percentage": "", "date": date_raw, "duration": 0,
            "isin": "", "agente_colocador": "", "series_count": 0, "url": url,
        }]

    return [{
        "name": name, "instrument": instrument, "qualification": qualification,
        "percentage": s.get("percentage", ""), "date": date_raw,
        "duration": parse_duration(s.get("duration", "")),
        "isin": s.get("isin", ""), "agente_colocador": s.get("agente_colocador", ""),
        "series_count": series_count, "url": url,
    } for s in series_data]


def build_email_html(entries):
    """Build HTML email with all bonds, highlighting >11% interest."""
    total = len(entries)
    high = [e for e in entries if parse_percentage(e["percentage"]) > INTEREST_THRESHOLD]
    high_count = len(high)

    rows = ""
    for e in entries:
        pct = parse_percentage(e["percentage"])
        style = ' style="background-color: #fff3cd; font-weight: bold;"' if pct > INTEREST_THRESHOLD else ""
        sc = f" ({e['series_count']} series)" if e.get("series_count", 0) > 1 else ""
        rows += f"""<tr{style}>
            <td style="padding:8px;border:1px solid #ddd;">{e['name']}{sc}</td>
            <td style="padding:8px;border:1px solid #ddd;">{e['instrument']}</td>
            <td style="padding:8px;border:1px solid #ddd;">{e['qualification']}</td>
            <td style="padding:8px;border:1px solid #ddd;">{e['percentage']}</td>
            <td style="padding:8px;border:1px solid #ddd;">{e['date']}</td>
            <td style="padding:8px;border:1px solid #ddd;">{e['duration']} días</td>
            <td style="padding:8px;border:1px solid #ddd;">{e.get('isin','')}</td>
            <td style="padding:8px;border:1px solid #ddd;">{e.get('agente_colocador','')}</td>
        </tr>"""

    return f"""<html><body>
    <h2>BVA Nuevas Emisiones - Reporte</h2>
    <p><strong>{total}</strong> series encontradas, <strong style="color:{'red' if high_count else 'green'}">{high_count}</strong> con tasa &gt; {INTEREST_THRESHOLD}%</p>
    {'<h3 style="color:red;">⚠️ Bonos con tasa mayor a ' + str(INTEREST_THRESHOLD) + '%:</h3><ul>' + ''.join(f'<li><strong>{e["name"]}</strong> — {e["percentage"]} ({e["duration"]} días) — ISIN: {e.get("isin","")}</li>' for e in high) + '</ul><hr>' if high_count else ''}
    <table style="border-collapse:collapse;width:100%;font-family:sans-serif;font-size:14px;">
    <tr style="background:#333;color:white;">
        <th style="padding:8px;border:1px solid #ddd;">Nombre</th>
        <th style="padding:8px;border:1px solid #ddd;">Instrumento</th>
        <th style="padding:8px;border:1px solid #ddd;">Calificación</th>
        <th style="padding:8px;border:1px solid #ddd;">Tasa</th>
        <th style="padding:8px;border:1px solid #ddd;">Fecha</th>
        <th style="padding:8px;border:1px solid #ddd;">Plazo</th>
        <th style="padding:8px;border:1px solid #ddd;">ISIN</th>
        <th style="padding:8px;border:1px solid #ddd;">Agente Colocador</th>
    </tr>
    {rows}
    </table>
    </body></html>"""


def send_email(entries):
    """Send email via Resend API."""
    import resend

    api_key = os.getenv("RESEND_API_KEY")
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")

    if not all([api_key, email_from, email_to]):
        print("⚠️  Missing email config (RESEND_API_KEY, EMAIL_FROM, EMAIL_TO). Skipping email.")
        return

    resend.api_key = api_key
    high_count = sum(1 for e in entries if parse_percentage(e["percentage"]) > INTEREST_THRESHOLD)
    subject = f"BVA Emisiones: {len(entries)} series"
    if high_count:
        subject += f" — ⚠️ {high_count} con tasa >{INTEREST_THRESHOLD}%"

    resend.Emails.send({
        "from": email_from,
        "to": [t.strip() for t in email_to.split(",")],
        "subject": subject,
        "html": build_email_html(entries),
    })
    print(f"✅ Email sent to {email_to}")


def ingest_mempalace():
    """Mine data/ into mempalace."""
    if not MEMPALACE_BIN:
        print("❌ mempalace not found in PATH", file=sys.stderr)
        return
    data_dir = str(Path(__file__).parent / "data")
    cmd = [MEMPALACE_BIN, "mine", data_dir, "--wing", "bva-emisiones"]
    print(f"🧠 Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ MemPalace ingestion complete\n{result.stdout}")
    else:
        print(f"❌ MemPalace error: {result.stderr}", file=sys.stderr)


def update_agent_md(entries):
    """Update AGENT.md execution-log with timestamp and summary."""
    agent_path = Path(__file__).parent / "AGENT.md"
    if not agent_path.exists():
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    high = sum(1 for e in entries if parse_percentage(e["percentage"]) > INTEREST_THRESHOLD)
    new_log = (
        f"### Room: execution-log\n\n"
        f"Last execution: {now}\n"
        f"Series scraped: {len(entries)}\n"
        f"High-yield bonds (>{INTEREST_THRESHOLD}%): {high}\n"
        f"Schedule: every Wednesday at 12:00 UTC (~08:00 PYT).\n"
        f"Output location: `data/emisiones.json`"
    )
    text = agent_path.read_text()
    text = re.sub(
        r"### Room: execution-log\n\n.*?(?=\n### |\Z)",
        new_log,
        text,
        flags=re.DOTALL,
    )
    agent_path.write_text(text)


def main():
    parser = argparse.ArgumentParser(description="BVA Emissions Scraper")
    parser.add_argument("--local", action="store_true", help="Also ingest into mempalace")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email")
    args = parser.parse_args()

    print("🔍 Fetching detail URLs...")
    urls = get_detail_urls(30)
    print(f"   Found {len(urls)} emissions")

    print("📄 Parsing detail pages...")
    entries = []
    for i, url in enumerate(urls, 1):
        print(f"   [{i}/{len(urls)}] {url.split('/')[-2]}")
        try:
            entries.extend(parse_emission(url))
        except Exception as e:
            print(f"   ⚠️  Error parsing {url}: {e}", file=sys.stderr)

    print(f"   Total series entries: {len(entries)}")

    # Save JSON
    out = Path(__file__).parent / "data" / "emisiones.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
    print(f"💾 Saved to {out}")

    update_agent_md(entries)

    # Email
    if not args.no_email:
        send_email(entries)

    # MemPalace (local only)
    if args.local:
        ingest_mempalace()

    # Print summary
    high = [e for e in entries if parse_percentage(e["percentage"]) > INTEREST_THRESHOLD]
    if high:
        print(f"\n🔥 {len(high)} series with interest > {INTEREST_THRESHOLD}%:")
        for e in high:
            print(f"   {e['name']} — {e['percentage']} ({e['duration']} días)")


if __name__ == "__main__":
    main()
