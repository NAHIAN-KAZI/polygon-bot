"""Money as the bank sends it (poisha) and as the customer reads it (Tk). Pure helpers, no I/O."""


def to_poisha(value: object) -> int | None:
    """An amount the bank sent as a number or numeric string, in poisha; None when it is not a number."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def tk(poisha: int | float | None) -> str | None:
    """'Tk 12,345.50' (never the taka sign: some models misread it as a digit). Whole taka drop the decimals."""
    if poisha is None:
        return None
    taka = poisha / 100
    return f"Tk {taka:,.0f}" if abs(taka - round(taka)) < 0.005 else f"Tk {taka:,.2f}"


def percent(part: float, whole: float) -> float | None:
    """part as a percentage of whole, one decimal; None when whole is not positive."""
    return round(100.0 * part / whole, 1) if whole and whole > 0 else None
