"""Exact money handling.

Amounts are integers in the smallest currency unit (centavos for CLP-style
amounts) so no floating point rounding leaks into invoices or stock totals.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CENTS = Decimal("100")


@dataclass(frozen=True, order=True)
class Money:
    cents: int = 0

    @classmethod
    def from_decimal(cls, value: Decimal | int | str) -> "Money":
        quantized = (Decimal(value) * CENTS).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return cls(int(quantized))

    @classmethod
    def from_float(cls, value: float) -> "Money":
        return cls.from_decimal(Decimal(str(value)))

    @property
    def as_decimal(self) -> Decimal:
        return (Decimal(self.cents) / CENTS).quantize(Decimal("0.01"))

    def __add__(self, other: "Money") -> "Money":
        return Money(self.cents + other.cents)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self.cents - other.cents)

    def __mul__(self, factor: int | Decimal) -> "Money":
        if isinstance(factor, int):
            return Money(self.cents * factor)
        return Money.from_decimal((self.as_decimal * Decimal(factor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def __neg__(self) -> "Money":
        return Money(-self.cents)

    def __str__(self) -> str:
        return f"{self.as_decimal:.2f}"


DEFAULT_IVA_RATE = Decimal("0.19")


def split_iva(gross: Money, rate: Decimal = DEFAULT_IVA_RATE) -> tuple[Money, Money]:
    """Split a gross (IVA-included) amount into (net, iva).

    The IVA is computed on the net and the net absorbs the rounding remainder so
    that net + iva always equals gross exactly.
    """
    net_cents = int(
        (Decimal(gross.cents) / (1 + rate)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    return Money(net_cents), Money(gross.cents - net_cents)


def add_iva(net: Money, rate: Decimal = DEFAULT_IVA_RATE) -> tuple[Money, Money]:
    """Given a net amount, return (net, iva) with iva rounded once."""
    iva = Money.from_decimal((net.as_decimal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return net, iva
