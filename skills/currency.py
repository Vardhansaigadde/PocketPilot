"""Currency conversion with today's rates (Frankfurter, free, no key, European Central Bank data)."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from .common import SkillError

DESCRIPTION = "Convert money between currencies at today's rate (e.g. 100 dollars to rupees)."
URL = "https://api.frankfurter.dev/v1/latest"

# Spoken names -> currency code (Frankfurter supports these).
NAMES = {
    "dollar": "USD", "dollars": "USD", "usd": "USD", "us dollar": "USD", "us dollars": "USD", "$": "USD",
    "rupee": "INR", "rupees": "INR", "inr": "INR", "rs": "INR", "indian rupee": "INR", "indian rupees": "INR",
    "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "pound": "GBP", "pounds": "GBP", "gbp": "GBP", "sterling": "GBP", "british pound": "GBP",
    "yen": "JPY", "jpy": "JPY", "japanese yen": "JPY",
    "yuan": "CNY", "cny": "CNY", "renminbi": "CNY",
    "singapore dollar": "SGD", "singapore dollars": "SGD", "sgd": "SGD",
    "australian dollar": "AUD", "australian dollars": "AUD", "aud": "AUD",
    "canadian dollar": "CAD", "canadian dollars": "CAD", "cad": "CAD",
    "swiss franc": "CHF", "swiss francs": "CHF", "franc": "CHF", "francs": "CHF", "chf": "CHF",
    "won": "KRW", "korean won": "KRW", "krw": "KRW",
    "ringgit": "MYR", "myr": "MYR", "baht": "THB", "thb": "THB", "rand": "ZAR", "zar": "ZAR",
    "hong kong dollar": "HKD", "hkd": "HKD", "new zealand dollar": "NZD", "nzd": "NZD",
}
UNSUPPORTED = {"dirham": "UAE dirham", "dirhams": "UAE dirham", "aed": "UAE dirham",
               "riyal": "Saudi riyal", "riyals": "Saudi riyal", "sar": "Saudi riyal",
               "taka": "taka", "bitcoin": "bitcoin"}
SYMBOL = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


class CurrencyInput(BaseModel):
    amount: float = Field(default=1, gt=0, le=1e12)
    from_cur: str = Field(min_length=3, max_length=3)
    to_cur: str = Field(default="INR", min_length=3, max_length=3)


def code(name: str) -> str | None:
    """'US dollars' -> 'USD'. None if it isn't a currency we know."""
    n = " ".join(name.lower().replace(".", "").split())
    if n in NAMES:
        return NAMES[n]
    if len(n) == 3 and n.upper() in set(NAMES.values()):
        return n.upper()
    return None


def _money(amount: float, cur: str) -> str:
    text = f"{amount:,.2f}".rstrip("0").rstrip(".")
    sym = SYMBOL.get(cur)
    return f"{sym}{text}" if sym else f"{text} {cur}"


def convert(client: httpx.Client, amount: float, from_cur: str, to_cur: str = "INR") -> str:
    q = CurrencyInput(amount=amount, from_cur=from_cur.upper(), to_cur=to_cur.upper())
    if q.from_cur == q.to_cur:
        return f"That's the same currency: {_money(q.amount, q.to_cur)}."
    r = client.get(URL, params={"from": q.from_cur, "to": q.to_cur, "amount": q.amount})
    if r.status_code == 404:
        raise SkillError(f"I don't have rates for {q.from_cur} to {q.to_cur}.")
    r.raise_for_status()
    data = r.json()
    value = data.get("rates", {}).get(q.to_cur)
    if value is None:
        raise SkillError(f"I don't have rates for {q.from_cur} to {q.to_cur}.")
    return f"{_money(q.amount, q.from_cur)} is {_money(value, q.to_cur)} (rate of {data.get('date', 'today')})."
