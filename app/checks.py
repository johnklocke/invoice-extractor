"""Checks extracted invoices for the problems that cost small businesses money:
math errors, duplicate bills, missing details and missed due dates."""
from datetime import date

from .models import Invoice, Issue

TOLERANCE = 0.02  # allow a cent or two of rounding


def _off(a: float, b: float) -> bool:
    return abs(a - b) > TOLERANCE


def check_invoice(inv: Invoice, today: date) -> None:
    for field_name, label in [("vendor", "vendor"), ("invoice_number", "invoice number"),
                              ("invoice_date", "invoice date"), ("total", "total")]:
        if getattr(inv, field_name) in (None, ""):
            inv.issues.append(Issue("error", f"Missing {label}."))

    for item in inv.line_items:
        if None not in (item.quantity, item.unit_price, item.amount) and _off(item.quantity * item.unit_price, item.amount):
            inv.issues.append(Issue("error", f"Line '{item.description}': {item.quantity:g} × ${item.unit_price:,.2f} "
                                             f"≠ ${item.amount:,.2f}."))

    amounts = [i.amount for i in inv.line_items if i.amount is not None]
    if amounts and inv.subtotal is not None and _off(sum(amounts), inv.subtotal):
        inv.issues.append(Issue("error", f"Line items add up to ${sum(amounts):,.2f}, "
                                         f"but the subtotal says ${inv.subtotal:,.2f}."))

    if None not in (inv.subtotal, inv.tax, inv.total) and _off(inv.subtotal + inv.tax, inv.total):
        inv.issues.append(Issue("error", f"Subtotal ${inv.subtotal:,.2f} + tax ${inv.tax:,.2f} = "
                                         f"${inv.subtotal + inv.tax:,.2f}, but the total says ${inv.total:,.2f}."))

    if inv.total is not None and inv.total <= 0:
        inv.issues.append(Issue("warning", "Total is zero or negative (credit memo?)."))

    if inv.due_date:
        try:
            due = date.fromisoformat(inv.due_date)
            if due < today:
                inv.issues.append(Issue("warning", f"Past due: was due {due:%b} {due.day}, {due.year} "
                                                   f"({(today - due).days} days ago)."))
        except ValueError:
            pass


def check_duplicates(invoices: list[Invoice]) -> None:
    """Flag the same bill uploaded twice: same vendor + invoice number,
    or same vendor + date + total when the number is missing."""
    seen: dict[tuple, str] = {}
    for inv in invoices:
        vendor = (inv.vendor or "").strip().lower()
        keys = []
        if vendor and inv.invoice_number:
            keys.append(("num", vendor, inv.invoice_number.strip().lower()))
        if vendor and inv.invoice_date and inv.total is not None:
            keys.append(("amt", vendor, inv.invoice_date, inv.total))
        match = next((seen[k] for k in keys if k in seen), None)
        if match:
            inv.issues.append(Issue("error", f"Possible duplicate of {match}."))
        for k in keys:
            seen.setdefault(k, inv.file_name)


def check_batch(invoices: list[Invoice], today: date | None = None) -> list[Invoice]:
    today = today or date.today()
    for inv in invoices:
        check_invoice(inv, today)
    check_duplicates(invoices)
    return invoices
