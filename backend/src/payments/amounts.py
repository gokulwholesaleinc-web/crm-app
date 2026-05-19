"""Stripe amount conversion helpers."""

from decimal import ROUND_HALF_UP, Decimal

# Stripe expects these currencies as whole units, not cents.
ZERO_DECIMAL_CURRENCIES = {
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "JPY",
    "KMF",
    "KRW",
    "MGA",
    "PYG",
    "RWF",
    "UGX",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
}


def normalize_currency(currency: str) -> str:
    code = (currency or "").upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("Currency must be a three-letter ISO code")
    return code


def currency_exponent(currency: str) -> int:
    return 0 if normalize_currency(currency) in ZERO_DECIMAL_CURRENCIES else 2


def to_stripe_minor_units(amount: float | int | Decimal | str, currency: str) -> int:
    """Convert a display amount to Stripe's integer minor-unit amount."""
    exponent = currency_exponent(currency)
    dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    quantizer = Decimal("1") if exponent == 0 else Decimal("0.01")
    normalized = dec.quantize(quantizer, rounding=ROUND_HALF_UP)
    return int((normalized * (Decimal(10) ** exponent)).quantize(Decimal("1")))


def from_stripe_minor_units(amount: int | str, currency: str) -> Decimal:
    """Convert Stripe's integer minor-unit amount to a display Decimal."""
    exponent = currency_exponent(currency)
    dec = Decimal(int(amount)) / (Decimal(10) ** exponent)
    quantizer = Decimal("1") if exponent == 0 else Decimal("0.01")
    return dec.quantize(quantizer, rounding=ROUND_HALF_UP)
