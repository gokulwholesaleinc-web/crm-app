"""Multi-currency configuration with static exchange rates.

Exchange rates are relative to USD as the base.
Rates can be overridden via environment variables with the pattern:
  EXCHANGE_RATE_EUR=0.92
  EXCHANGE_RATE_GBP=0.79
"""

import os
from typing import Dict

# Supported currencies with ISO 4217 codes
SUPPORTED_CURRENCIES = {
    "USD": {"name": "US Dollar", "symbol": "$"},
    "EUR": {"name": "Euro", "symbol": "\u20ac"},
    "GBP": {"name": "British Pound", "symbol": "\u00a3"},
    "JPY": {"name": "Japanese Yen", "symbol": "\u00a5"},
    "CAD": {"name": "Canadian Dollar", "symbol": "CA$"},
    "AUD": {"name": "Australian Dollar", "symbol": "A$"},
    "CHF": {"name": "Swiss Franc", "symbol": "CHF"},
    "CNY": {"name": "Chinese Yuan", "symbol": "\u00a5"},
    "INR": {"name": "Indian Rupee", "symbol": "\u20b9"},
    "BRL": {"name": "Brazilian Real", "symbol": "R$"},
    "MXN": {"name": "Mexican Peso", "symbol": "MX$"},
    "SGD": {"name": "Singapore Dollar", "symbol": "S$"},
    "HKD": {"name": "Hong Kong Dollar", "symbol": "HK$"},
    "KRW": {"name": "South Korean Won", "symbol": "\u20a9"},
    "SEK": {"name": "Swedish Krona", "symbol": "kr"},
    "NOK": {"name": "Norwegian Krone", "symbol": "kr"},
    "NZD": {"name": "New Zealand Dollar", "symbol": "NZ$"},
    "ZAR": {"name": "South African Rand", "symbol": "R"},
    "AED": {"name": "UAE Dirham", "symbol": "AED"},
    "SAR": {"name": "Saudi Riyal", "symbol": "SAR"},
}

# Static exchange rates to USD (how many of the currency per 1 USD)
_DEFAULT_RATES_TO_USD: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 149.50,
    "CAD": 1.36,
    "AUD": 1.53,
    "CHF": 0.88,
    "CNY": 7.24,
    "INR": 83.10,
    "BRL": 4.97,
    "MXN": 17.15,
    "SGD": 1.34,
    "HKD": 7.82,
    "KRW": 1320.0,
    "SEK": 10.42,
    "NOK": 10.55,
    "NZD": 1.63,
    "ZAR": 18.65,
    "AED": 3.67,
    "SAR": 3.75,
}

# Default base currency for the application
BASE_CURRENCY = os.environ.get("CRM_BASE_CURRENCY", "USD")


def _load_exchange_rates() -> Dict[str, float]:
    """Load exchange rates, allowing env variable overrides."""
    rates = dict(_DEFAULT_RATES_TO_USD)
    for code in SUPPORTED_CURRENCIES:
        env_key = f"EXCHANGE_RATE_{code}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            try:
                rates[code] = float(env_val)
            except ValueError:
                pass
    return rates


EXCHANGE_RATES_TO_USD = _load_exchange_rates()


def convert_amount(
    amount: float,
    from_currency: str,
    to_currency: str,
) -> float:
    """Convert an amount from one currency to another using static rates.

    Args:
        amount: The amount to convert.
        from_currency: ISO 4217 code of source currency.
        to_currency: ISO 4217 code of target currency.

    Returns:
        Converted amount rounded to 2 decimal places.
    """
    if from_currency == to_currency:
        return round(amount, 2)

    from_rate = EXCHANGE_RATES_TO_USD.get(from_currency, 1.0)
    to_rate = EXCHANGE_RATES_TO_USD.get(to_currency, 1.0)

    # Convert: source -> USD -> target
    usd_amount = amount / from_rate
    converted = usd_amount * to_rate
    return round(converted, 2)


def get_currency_symbol(currency_code: str) -> str:
    """Get the symbol for a currency code."""
    info = SUPPORTED_CURRENCIES.get(currency_code)
    return info["symbol"] if info else currency_code


def get_supported_currencies_list() -> list:
    """Get list of supported currencies for API response."""
    return [
        {
            "code": code,
            "name": info["name"],
            "symbol": info["symbol"],
            "exchange_rate": EXCHANGE_RATES_TO_USD.get(code, 1.0),
        }
        for code, info in SUPPORTED_CURRENCIES.items()
    ]


def get_base_currency() -> str:
    """Get the configured base currency."""
    return BASE_CURRENCY
