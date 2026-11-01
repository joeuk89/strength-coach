from coach.core.config import Units

KG_PER_LB = 0.45359237
KG_PRECISION = 4


def to_kg(amount: float, units: Units) -> float:
    """A load in athlete units as the kilograms Hevy stores."""
    return amount if units == "kg" else round(amount * KG_PER_LB, KG_PRECISION)


def from_kg(kg: float, units: Units) -> float:
    """Hevy kilograms in athlete units, unrounded."""
    return kg if units == "kg" else kg / KG_PER_LB
