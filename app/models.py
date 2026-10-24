from dataclasses import asdict, dataclass, field


@dataclass
class LineItem:
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None


@dataclass
class Issue:
    level: str  # "error" (needs a person) or "warning" (worth knowing)
    message: str


@dataclass
class Invoice:
    file_name: str
    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None  # ISO yyyy-mm-dd
    due_date: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    currency: str = "USD"
    line_items: list[LineItem] = field(default_factory=list)
    extracted_by: str = ""  # "claude" or "text rules"
    issues: list[Issue] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(i.level == "error" for i in self.issues):
            return "Review"
        if self.issues:
            return "OK, see note"
        return "OK"

    def to_dict(self) -> dict:
        return {**asdict(self), "status": self.status}
