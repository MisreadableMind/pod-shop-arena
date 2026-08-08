"""Money is an integer count of minor units plus a currency code. Never a float.

A float dollar amount is a different number on different machines once you have
divided by it a few times, and different numbers give different Merkle roots for
the same evidence. That would make the anchor meaningless, so the type system
refuses to represent money as a float at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Minor units per major unit. Anything not listed defaults to 2, which is right
# far more often than it is wrong, but the explicit table is what we trust.
_EXPONENTS: dict[str, int] = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CHF": 2,
    "CAD": 2,
    "AUD": 2,
    "HKD": 2,
    "SGD": 2,
    "JPY": 0,
    "KRW": 0,
    "BTC": 8,
    "ETH": 18,
}

DEFAULT_EXPONENT = 2


def exponent_for(currency: str) -> int:
    return _EXPONENTS.get(currency.upper(), DEFAULT_EXPONENT)


class CurrencyMismatch(ValueError):
    """Two amounts in different currencies met. There is no sane default here."""


@dataclass(frozen=True, slots=True, order=False)
class Money:
    minor: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.minor, int) or isinstance(self.minor, bool):
            raise TypeError(f"minor units must be int, got {type(self.minor).__name__}")
        if not self.currency or len(self.currency) > 5:
            raise ValueError(f"implausible currency code: {self.currency!r}")
        object.__setattr__(self, "currency", self.currency.upper())

    # -- construction ----------------------------------------------------

    @classmethod
    def from_decimal(cls, amount: Decimal, currency: str) -> Money:
        """Exact only. A sub-minor-unit amount is a bug in the caller, not
        something to round away quietly."""
        if not isinstance(amount, Decimal):
            raise TypeError("build Money from Decimal or int, never float")
        scaled = amount * (10 ** exponent_for(currency))
        if scaled != scaled.to_integral_value():
            raise ValueError(
                f"{amount} {currency} is finer than one minor unit; "
                "quantize deliberately before constructing Money"
            )
        return cls(int(scaled), currency)

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(0, currency)

    # -- conversion ------------------------------------------------------

    def as_decimal(self) -> Decimal:
        return Decimal(self.minor).scaleb(-exponent_for(self.currency))

    # -- arithmetic ------------------------------------------------------

    def _check(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(f"{self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.minor - other.minor, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.minor, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.minor), self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.minor < other.minor

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.minor <= other.minor

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.minor > other.minor

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.minor >= other.minor

    def __bool__(self) -> bool:
        return self.minor != 0

    def __str__(self) -> str:
        return f"{self.as_decimal()} {self.currency}"


def sum_money(amounts: list[Money], currency: str) -> Money:
    total = Money.zero(currency)
    for a in amounts:
        total = total + a
    return total
