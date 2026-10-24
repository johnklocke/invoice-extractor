"""Pulls structured data out of an invoice or receipt.

With ANTHROPIC_API_KEY set, Claude reads the PDF or photo directly, so it works
on any layout, scans and phone pictures included. Without a key, a text-rules
parser handles typed PDFs that use common labels ("Invoice #", "Subtotal",
"Total"). That covers the bundled samples and lets the demo run offline.
"""
import base64
import io
import os
import re
from datetime import datetime

from .models import Invoice, Issue, LineItem

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp", ".gif": "image/gif"}

# ---------- shared helpers ----------

DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y",
                "%d %b %Y", "%d %B %Y", "%b. %d, %Y", "%m-%d-%Y"]


def to_iso_date(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = text.strip().rstrip(".")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def to_money(text: str | None) -> float | None:
    if text is None:
        return None
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(text))
    return round(float(m.group().replace(",", "")), 2) if m else None


# ---------- offline text-rules parser ----------

MONEY = r"\$?\s*(-?[\d,]+\.\d{2})"
LABELS = {
    "invoice_number": r"^(?:invoice|inv|bill)\s*(?:#|no\.?|number|num)\s*:?\s*([A-Za-z0-9][A-Za-z0-9\-/]*)",
    "invoice_date": r"^(?:invoice date|date of invoice|date issued|issue date|date)\s*:?\s*(.+)$",
    "due_date": r"^(?:due date|payment due|due on|due)\s*:?\s*(.+)$",
    "subtotal": rf"^sub\s*-?\s*total\s*:?\s*{MONEY}",
    "tax": rf"^(?:sales tax|tax|vat|gst|hst)\b[^$\d\n]*{MONEY}",
    "total": rf"^(?:total due|amount due|balance due|invoice total|grand total|total)\s*:?\s*{MONEY}",
}
ITEM = re.compile(rf"^(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+{MONEY}\s+{MONEY}$")
NOT_ITEMS = re.compile(r"^(sub\s*-?total|total|tax|sales tax|amount due|balance)", re.I)


def pdf_text(data: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def parse_text(text: str, file_name: str) -> Invoice:
    inv = Invoice(file_name=file_name, extracted_by="text rules")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        inv.issues.append(Issue("error", "No text found. This looks like a scan or photo; turn on AI mode to read it."))
        return inv
    inv.vendor = lines[0]
    for line in lines:
        for field_name, pattern in LABELS.items():
            if getattr(inv, field_name) is not None:
                continue
            m = re.match(pattern, line, re.I)
            if not m:
                continue
            value = m.group(1)
            if field_name.endswith("date"):
                value = to_iso_date(value)
            elif field_name != "invoice_number":
                value = to_money(value)
            if value is not None:
                setattr(inv, field_name, value)
                break
        m = ITEM.match(line)
        if m and not NOT_ITEMS.match(line):
            inv.line_items.append(LineItem(
                description=m["desc"], quantity=float(m["qty"]),
                unit_price=to_money(m.group(3)), amount=to_money(m.group(4)),
            ))
    return inv


# ---------- Claude parser ----------

PROMPT = """Extract the data from this invoice or receipt. Use null for anything not shown.
Dates must be yyyy-mm-dd. Amounts are plain numbers with no currency symbols.
vendor is the business that issued the document, not the customer."""

NULL_STR = {"type": ["string", "null"]}
NULL_NUM = {"type": ["number", "null"]}
TOOL = {
    "name": "record_invoice",
    "description": "Record the fields extracted from the invoice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor": NULL_STR, "invoice_number": NULL_STR,
            "invoice_date": NULL_STR, "due_date": NULL_STR,
            "currency": {"type": "string", "description": "ISO code, e.g. USD"},
            "subtotal": NULL_NUM, "tax": NULL_NUM, "total": NULL_NUM,
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"description": {"type": "string"}, "quantity": NULL_NUM,
                                   "unit_price": NULL_NUM, "amount": NULL_NUM},
                    "required": ["description"],
                },
            },
        },
        "required": ["vendor", "invoice_number", "invoice_date", "total", "line_items"],
    },
}


def parse_claude(data: bytes, file_name: str, media_type: str, client=None) -> Invoice:
    import anthropic

    client = client or anthropic.Anthropic()
    encoded = base64.standard_b64encode(data).decode()
    kind = "document" if media_type == "application/pdf" else "image"
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_invoice"},
        messages=[{"role": "user", "content": [
            {"type": kind, "source": {"type": "base64", "media_type": media_type, "data": encoded}},
            {"type": "text", "text": PROMPT},
        ]}],
    )
    d = next(block.input for block in response.content if block.type == "tool_use")
    return Invoice(
        file_name=file_name,
        vendor=d.get("vendor"),
        invoice_number=d.get("invoice_number"),
        invoice_date=to_iso_date(d.get("invoice_date")) or d.get("invoice_date"),
        due_date=to_iso_date(d.get("due_date")) or d.get("due_date"),
        subtotal=to_money(d.get("subtotal")),
        tax=to_money(d.get("tax")),
        total=to_money(d.get("total")),
        currency=d.get("currency") or "USD",
        line_items=[LineItem(description=i.get("description", ""), quantity=i.get("quantity"),
                             unit_price=to_money(i.get("unit_price")), amount=to_money(i.get("amount")))
                    for i in d.get("line_items", [])],
        extracted_by="claude",
    )


# ---------- entry point ----------

def media_type_for(file_name: str) -> str | None:
    ext = os.path.splitext(file_name.lower())[1]
    if ext == ".pdf":
        return "application/pdf"
    return IMAGE_TYPES.get(ext)


def extract(data: bytes, file_name: str) -> Invoice:
    media_type = media_type_for(file_name)
    if media_type is None:
        inv = Invoice(file_name=file_name)
        inv.issues.append(Issue("error", "Unsupported file type. Use PDF, PNG, JPG, WEBP or GIF."))
        return inv

    fallback_note = ""
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return parse_claude(data, file_name, media_type)
        except Exception as exc:  # network error, bad response, etc.
            fallback_note = f"AI extraction failed ({type(exc).__name__}); used text rules."

    if media_type != "application/pdf":
        inv = Invoice(file_name=file_name, extracted_by="text rules")
        inv.issues.append(Issue("error", "Photos and images need AI mode. Add an ANTHROPIC_API_KEY to read them."))
        return inv

    try:
        inv = parse_text(pdf_text(data), file_name)
    except Exception as exc:  # corrupt or encrypted PDF
        inv = Invoice(file_name=file_name, extracted_by="text rules")
        inv.issues.append(Issue("error", f"Could not read this PDF ({type(exc).__name__})."))
    if fallback_note:
        inv.issues.append(Issue("warning", fallback_note))
    return inv
