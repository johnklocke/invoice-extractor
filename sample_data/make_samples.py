"""Generates the sample invoices in sample_data/invoices/ (fictional vendors).

Run:  python sample_data/make_samples.py

The set is built to exercise the checks:
  01 clean invoice
  02 clean invoice, different layout and labels
  03 line items don't add up to the subtotal
  04 exact duplicate of 01 (same vendor and invoice number)
  05 past due, and tax + subtotal doesn't match total
  06 clean invoice with a long line-item list
"""
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "invoices"


def money(x: float) -> str:
    return f"${x:,.2f}"


def draw(path, vendor, vendor_lines, labels, meta, bill_to, items, subtotal, tax, total, color, total_label="Total"):
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    c.setFillColor(HexColor(color))
    c.rect(0, h - 1.1 * inch, w, 1.1 * inch, stroke=0, fill=1)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 20)
    c.drawString(0.7 * inch, h - 0.6 * inch, vendor)
    c.setFont("Helvetica", 9)
    for i, line in enumerate(vendor_lines):
        c.drawString(0.7 * inch, h - 0.82 * inch - i * 11, line)

    c.setFillColor(HexColor("#1B1F24"))
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(w - 0.7 * inch, h - 1.5 * inch, labels["title"])
    c.setFont("Helvetica", 10)
    y = h - 1.8 * inch
    for label, value in meta:
        c.drawRightString(w - 0.7 * inch, y, f"{label} {value}")
        y -= 14

    c.setFont("Helvetica-Bold", 10)
    c.drawString(0.7 * inch, h - 1.5 * inch, "Bill To")
    c.setFont("Helvetica", 10)
    for i, line in enumerate(bill_to):
        c.drawString(0.7 * inch, h - 1.68 * inch - i * 13, line)

    y = h - 3.0 * inch
    cols = [0.7 * inch, 4.6 * inch, 5.6 * inch, w - 0.7 * inch]
    c.setFont("Helvetica-Bold", 10)
    c.drawString(cols[0], y, "Description")
    c.drawRightString(cols[1] + 0.3 * inch, y, "Qty")
    c.drawRightString(cols[2] + 0.5 * inch, y, labels.get("price", "Unit Price"))
    c.drawRightString(cols[3], y, "Amount")
    c.line(cols[0], y - 5, cols[3], y - 5)
    c.setFont("Helvetica", 10)
    y -= 20
    for desc, qty, price, amount in items:
        c.drawString(cols[0], y, desc)
        c.drawRightString(cols[1] + 0.3 * inch, y, f"{qty:g}")
        c.drawRightString(cols[2] + 0.5 * inch, y, money(price))
        c.drawRightString(cols[3], y, money(amount))
        y -= 16

    y -= 10
    c.line(cols[2] - 0.6 * inch, y + 8, cols[3], y + 8)
    for label, value, bold in [("Subtotal", subtotal, False), (labels.get("tax", "Tax"), tax, False), (total_label, total, True)]:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(cols[2] + 0.5 * inch, y, label)
        c.drawRightString(cols[3], y, money(value))
        y -= 16

    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#5B6470"))
    c.drawString(0.7 * inch, 0.6 * inch, labels.get("footer", "Thank you for your business."))
    c.save()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bill_to = ["Main St Bakery", "42 Main St", "Springfield"]

    acme_items = [("Copy paper, case of 10 reams", 4, 42.00, 168.00),
                  ("Toner cartridge, black", 2, 89.50, 179.00),
                  ("Shipping boxes, pack of 25", 3, 31.25, 93.75)]
    acme = dict(vendor="Acme Office Supply", vendor_lines=["500 Commerce Dr, Springfield", "billing@acme-office.example"],
                labels={"title": "INVOICE"}, bill_to=bill_to, items=acme_items,
                subtotal=440.75, tax=30.85, total=471.60, color="#2E5E4E",
                meta=[("Invoice #:", "INV-1042"), ("Invoice Date:", "Oct 3, 2026"), ("Due Date:", "Nov 2, 2026")])
    draw(OUT / "01_acme_office_supply.pdf", **acme)
    draw(OUT / "04_acme_office_supply_resent.pdf", **acme)

    draw(OUT / "02_northwind_plumbing.pdf", vendor="Northwind Plumbing",
         vendor_lines=["Licensed & insured", "(555) 014-7788"],
         labels={"title": "SERVICE INVOICE", "price": "Rate", "tax": "Sales Tax"},
         meta=[("Invoice No.", "2231"), ("Date:", "10/07/2026"), ("Payment Due:", "11/06/2026")],
         bill_to=bill_to,
         items=[("Service call, after hours", 1, 175.00, 175.00),
                ("Replace commercial faucet", 1, 310.00, 310.00),
                ("Labor (hours)", 2.5, 95.00, 237.50)],
         subtotal=722.50, tax=50.58, total=773.08, color="#1F4E79", total_label="Amount Due")

    draw(OUT / "03_brightline_electric.pdf", vendor="Brightline Electric",
         vendor_lines=["Commercial electrical", "ap@brightline.example"],
         labels={"title": "INVOICE"},
         meta=[("Invoice #:", "BE-0087"), ("Invoice Date:", "2026-10-12"), ("Due Date:", "2026-11-11")],
         bill_to=bill_to,
         items=[("LED fixture replacement", 8, 64.00, 512.00),
                ("Dedicated 20A circuit for oven", 1, 425.00, 425.00),
                ("Permit fee", 1, 85.00, 85.00)],
         subtotal=1122.00, tax=78.54, total=1200.54, color="#7A3E00")  # items add to 1,022.00

    draw(OUT / "05_lakeside_janitorial.pdf", vendor="Lakeside Janitorial",
         vendor_lines=["Nightly & weekly cleaning", "office@lakeside-clean.example"],
         labels={"title": "INVOICE"},
         meta=[("Invoice #:", "LJ-5510"), ("Invoice Date:", "August 28, 2026"), ("Due Date:", "September 27, 2026")],
         bill_to=bill_to,
         items=[("Nightly cleaning, August", 1, 1450.00, 1450.00),
                ("Floor strip and wax", 1, 380.00, 380.00)],
         subtotal=1830.00, tax=128.10, total=1985.10, color="#4B3F72")  # 1830 + 128.10 = 1958.10

    draw(OUT / "06_greenway_food_distributors.pdf", vendor="Greenway Food Distributors",
         vendor_lines=["Wholesale bakery ingredients", "orders@greenway-foods.example"],
         labels={"title": "INVOICE"},
         meta=[("Invoice #:", "GW-77812"), ("Invoice Date:", "Oct 15, 2026"), ("Due Date:", "Oct 29, 2026")],
         bill_to=bill_to,
         items=[("All-purpose flour, 50 lb", 12, 24.80, 297.60),
                ("Granulated sugar, 50 lb", 6, 38.40, 230.40),
                ("Unsalted butter, case", 5, 96.00, 480.00),
                ("Large eggs, 15 dozen", 8, 41.25, 330.00),
                ("Vanilla extract, 1 gal", 1, 118.00, 118.00),
                ("Parchment sheets, 1000 ct", 2, 54.90, 109.80)],
         subtotal=1565.80, tax=0.00, total=1565.80, color="#3B6D11")
    print(f"Wrote samples to {OUT}")


if __name__ == "__main__":
    main()
