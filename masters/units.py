from decimal import Decimal


def convert(qty, from_unit, to_unit):
    """Convert a quantity between units of the same dimension (e.g. g to kg)."""
    if from_unit.dimension != to_unit.dimension:
        raise ValueError(f"Cannot convert {from_unit.code} to {to_unit.code}")
    return Decimal(qty) * from_unit.to_base / to_unit.to_base