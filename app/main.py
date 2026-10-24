"""Invoice & Receipt Extractor: FastAPI app.

Run:   uvicorn app.main:app --reload
Open:  http://localhost:8000      (upload page)
       http://localhost:8000/docs (API docs)
"""
import html
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY etc. from a .env file if present

from fastapi import FastAPI, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import HTMLResponse, Response  # noqa: E402

from .checks import check_batch  # noqa: E402
from .export import to_excel  # noqa: E402
from .extract import extract  # noqa: E402
from .models import Invoice, Issue  # noqa: E402

SAMPLES = Path(__file__).parent.parent / "sample_data" / "invoices"
MAX_BYTES = 20 * 1024 * 1024

app = FastAPI(
    title="Invoice & Receipt Extractor",
    description="Turns invoice PDFs and receipt photos into a clean spreadsheet and flags errors and duplicates.",
    version="1.0.0",
)

BATCHES: dict[str, list[Invoice]] = {}  # in-memory store; swap for a database in production


def mode() -> str:
    return "Claude AI" if os.getenv("ANTHROPIC_API_KEY") else "Offline text rules"


def run_batch(files: list[tuple[str, bytes]]) -> str:
    invoices = []
    for name, data in files:
        if len(data) > MAX_BYTES:
            inv = Invoice(file_name=name)
            inv.issues.append(Issue("error", "File is larger than 20 MB."))
            invoices.append(inv)
        else:
            invoices.append(extract(data, name))
    check_batch(invoices)
    batch_id = secrets.token_hex(4)
    BATCHES[batch_id] = invoices
    return batch_id


async def _read(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    return [(f.filename or "upload", await f.read()) for f in files]


def _batch(batch_id: str) -> list[Invoice]:
    if batch_id not in BATCHES:
        raise HTTPException(404, "Batch not found.")
    return BATCHES[batch_id]


# ---------- API ----------

@app.get("/health")
def health():
    return {"status": "ok", "mode": mode()}


@app.post("/api/extract")
async def api_extract(files: list[UploadFile]):
    batch_id = run_batch(await _read(files))
    return {"batch_id": batch_id, "excel_url": f"/batches/{batch_id}.xlsx",
            "invoices": [i.to_dict() for i in BATCHES[batch_id]]}


@app.get("/api/batches/{batch_id}")
def api_batch(batch_id: str):
    return [i.to_dict() for i in _batch(batch_id)]


@app.get("/batches/{batch_id}.xlsx")
def excel(batch_id: str):
    return Response(to_excel(_batch(batch_id)),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="invoices-{batch_id}.xlsx"'})


# ---------- Web pages ----------

STYLE = """
:root{--brand:#1f4e79;--ink:#1b1f24;--muted:#5b6470;--bg:#f6f7f9;--card:#fff;--line:#e6e9ee;--bad:#b3261e;--note:#8a5a00}
*{box-sizing:border-box} body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);background:var(--bg)}
header{background:var(--brand);color:#fff;padding:18px 24px} header h1{margin:0;font-size:22px}
header p{margin:4px 0 0;opacity:.85;font-size:14px}
main{max-width:1080px;margin:24px auto;padding:0 16px}
.card{background:var(--card);border-radius:12px;box-shadow:0 1px 3px #0001;padding:20px;margin-bottom:16px}
.drop{border:2px dashed #c9d3df;border-radius:12px;padding:28px;text-align:center;background:#fbfcfe}
button,.btn{background:var(--brand);color:#fff;border:0;border-radius:8px;padding:10px 16px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}
.ghost{background:#e8f0f8;color:var(--brand)} .muted{color:var(--muted);font-size:14px}
.badge{font-size:12px;padding:3px 8px;border-radius:10px;white-space:nowrap;background:#e8f0f8;color:var(--brand)}
.ok{background:#e6f4ea;color:#1e6b34} .review{background:#fdecea;color:var(--bad)} .note{background:#fff4e0;color:var(--note)}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.stat{background:#fff;border-radius:10px;box-shadow:0 1px 3px #0001;padding:12px 16px;min-width:150px}
.stat b{display:block;font-size:24px}
.scroll{overflow-x:auto} table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;white-space:nowrap} td.n{text-align:right;white-space:nowrap} td.d{white-space:nowrap}
ul.issues{margin:0;padding-left:16px} li.error{color:var(--bad)} li.warning{color:var(--note)}
"""


def page(body: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Invoice & Receipt Extractor</title>
<style>{STYLE}</style></head><body>
<header><h1>Invoice &amp; Receipt Extractor</h1>
<p>PDFs and photos in, clean spreadsheet out &middot; <span class="badge" style="background:#fff3;color:#fff">{mode()}</span></p></header>
<main>{body}</main></body></html>"""


@app.get("/", response_class=HTMLResponse)
def home():
    return page("""
<form class="card" method="post" action="/extract" enctype="multipart/form-data">
  <div class="drop">
    <p><b>Choose invoices or receipts</b> (PDF, PNG, JPG). Select as many as you like.</p>
    <input type="file" name="files" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.gif" required>
  </div>
  <p class="muted">Each file is read into vendor, invoice number, dates, line items and totals, then checked for
  math errors, duplicates, missing details and past-due bills.</p>
  <button type="submit">Extract</button>
</form>
<form method="post" action="/samples"><button class="ghost" type="submit">Try it with 6 sample invoices</button></form>""")


def results(batch_id: str) -> str:
    invs, e = BATCHES[batch_id], html.escape
    is_dup = lambda i: any(x.message.startswith("Possible duplicate") for x in i.issues)  # noqa: E731
    total = sum(i.total or 0 for i in invs if not is_dup(i))
    review = sum(1 for i in invs if i.status == "Review")
    past_due = sum(1 for i in invs if any(x.message.startswith("Past due") for x in i.issues))
    rows = ""
    for i in invs:
        cls = {"OK": "ok", "Review": "review"}.get(i.status, "note")
        issues = "".join(f"<li class='{x.level}'>{e(x.message)}</li>" for x in i.issues)
        rows += (f"<tr><td>{e(i.vendor or '-')}<br><span class=muted>{e(i.file_name)}</span></td>"
                 f"<td>{e(i.invoice_number or '-')}</td><td class=d>{e(i.invoice_date or '-')}</td><td class=d>{e(i.due_date or '-')}</td>"
                 f"<td class=n>{'' if i.total is None else f'${i.total:,.2f}'}</td>"
                 f"<td><span class='badge {cls}'>{e(i.status)}</span></td>"
                 f"<td>{'<ul class=issues>' + issues + '</ul>' if issues else ''}</td></tr>")
    return page(f"""
<div class="stats">
  <div class="stat"><b>{len(invs)}</b>documents</div>
  <div class="stat"><b>${total:,.2f}</b>total billed (duplicates excluded)</div>
  <div class="stat"><b>{review}</b>need review</div>
  <div class="stat"><b>{past_due}</b>past due</div>
</div>
<div class="card scroll"><table>
<tr><th>Vendor</th><th>Invoice #</th><th>Date</th><th>Due</th><th>Total</th><th>Status</th><th>Issues</th></tr>
{rows}</table></div>
<a class="btn" href="/batches/{batch_id}.xlsx">Download Excel</a>
<a class="btn ghost" href="/">Upload more</a>""")


@app.post("/extract", response_class=HTMLResponse)
async def extract_page(files: list[UploadFile]):
    return results(run_batch(await _read(files)))


@app.post("/samples", response_class=HTMLResponse)
def samples_page():
    files = [(p.name, p.read_bytes()) for p in sorted(SAMPLES.glob("*.pdf"))]
    return results(run_batch(files))
