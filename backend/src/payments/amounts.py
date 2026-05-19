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

# Stripe's only three-decimal currencies. Charges are submitted in
# thousandths (e.g. BHD 1.234 → 1234) and Stripe rounds the last digit
# to zero, so callers should still avoid sub-fil precision client-side.
THREE_DECIMAL_CURRENCIES = {
    "BHD",
    "JOD",
    "KWD",
    "OMR",
    "TND",
}


def normalize_currency(currency: str) -> str:
    code = (currency or "").upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("Currency must be a three-letter ISO code")
    return code


def currency_exponent(currency: str) -> int:
    code = normalize_currency(currency)
    if code in ZERO_DECIMAL_CURRENCIES:
        return 0
    if code in THREE_DECIMAL_CURRENCIES:
        return 3
    return 2


def _quantizer(exponent: int) -> Decimal:
    if exponent == 0:
        return Decimal("1")
    return Decimal("1").scaleb(-exponent)


def to_stripe_minor_units(amount: float | int | Decimal | str, currency: str) -> int:
    """Convert a display amount to Stripe's integer minor-unit amount."""
    exponent = currency_exponent(currency)
    dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    normalized = dec.quantize(_quantizer(exponent), rounding=ROUND_HALF_UP)
    return int((normalized * (Decimal(10) ** exponent)).quantize(Decimal("1")))


def from_stripe_minor_units(amount: int | str, currency: str) -> Decimal:
    """Convert Stripe's integer minor-unit amount to a display Decimal."""
    exponent = currency_exponent(currency)
    dec = Decimal(int(amount)) / (Decimal(10) ** exponent)
    return dec.quantize(_quantizer(exponent), rounding=ROUND_HALF_UP)
