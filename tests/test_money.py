from decimal import Decimal

import pytest

from app.money import Money, add_iva, split_iva


def test_from_decimal_rounds_half_up():
    assert Money.from_decimal("10.005").cents == 1001
    assert Money.from_decimal("10.004").cents == 1000


def test_from_float_uses_string_to_avoid_binary_error():
    assert Money.from_float(0.1).cents == 10
    assert Money.from_float(19.99).cents == 1999


def test_arithmetic_stays_integer():
    a = Money(1999)
    assert (a + Money(1)).cents == 2000
    assert (a * 3).cents == 5997
    assert (a - Money(1000)).cents == 999
    assert (-a).cents == -1999


def test_iva_split_is_exact():
    gross = Money(11900)
    net, iva = split_iva(gross)
    assert net.cents == 10000
    assert iva.cents == 1900
    assert net.cents + iva.cents == gross.cents


@pytest.mark.parametrize("gross_cents", [1, 7, 99, 12345, 999999])
def test_iva_split_never_loses_a_cent(gross_cents):
    net, iva = split_iva(Money(gross_cents))
    assert net.cents + iva.cents == gross_cents


def test_add_iva_is_additive():
    net, iva = add_iva(Money(10000))
    assert iva.cents == 1900
    assert (net + iva).cents == 11900


def test_custom_rate():
    net, iva = split_iva(Money(12100), rate=Decimal("0.21"))
    assert net.cents == 10000
    assert iva.cents == 2100
