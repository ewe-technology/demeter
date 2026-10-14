"""
Vectors for dec::Dec arithmetic: python `decimal` at prec 35 (demeter's context), random operands of 1-38 digits,
exponents -60..20, zeros, signs, near-equal subtractions and wide exponent gaps. One line per case:

    op  a  b  result        (each value as sign:coefficient:exponent, python's Decimal.as_tuple())

    python make_py_decimal_ops.py [cases] > out/py_decimal_ops.txt   # 2000 cases committed; 20000 checked once
"""
import random
import sys
from decimal import Decimal, getcontext

getcontext().prec = 35
random.seed(20261014)


def rnd() -> Decimal:
    r = random.random()
    if r < 0.05:
        return Decimal((random.randint(0, 1), (0,), random.randint(-60, 20)))   # a zero with some exponent
    digits = random.choice([1, 2, 5, 18, 29, 34, 35, 35, 35, 36, 38])
    coeff = random.randint(10 ** (digits - 1), 10 ** digits - 1) if digits > 1 else random.randint(1, 9)
    if random.random() < 0.2:
        coeff = coeff // 10 ** random.randint(1, 4) * 10 ** random.randint(1, 4) or 1   # trailing zeros
    while coeff >= 10 ** 38:   # a Dec holds 38 digits; python values in demeter have <= 35 (bigger ints take other paths)
        coeff //= 10
    return Decimal((random.randint(0, 1), tuple(int(c) for c in str(coeff)), random.randint(-60, 20)))


def fmt(d: Decimal) -> str:
    t = d.as_tuple()
    return f"{t.sign}:{''.join(map(str, t.digits))}:{t.exponent}"


for i in range(int(sys.argv[1]) if len(sys.argv) > 1 else 2000):
    a, b = rnd(), rnd()
    if i % 7 == 0:   # near-equal subtraction
        b = a.copy_negate() + Decimal((0, (1,), a.as_tuple().exponent - random.randint(0, 3))) if a else b
    if i % 11 == 0:   # wide exponent gap
        b = b.scaleb(random.choice([-90, -81, -80, -79, -45, 45, 80, 81, 90]))
    for op in ("add", "sub", "mul", "div", "sqrt"):
        try:
            if op == "add":
                r = a + b
            elif op == "sub":
                r = a - b
            elif op == "mul":
                r = a * b
            elif op == "div":
                if b == 0:
                    continue
                r = a / b
            else:
                if a < 0 or a == 0:
                    continue
                r = a.sqrt()
        except Exception:
            continue
        print(op, fmt(a), fmt(b), fmt(r))
