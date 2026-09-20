"""Abstention-guard wrapper: turns B2 / M1 / M2 into B2g / M1g / M2g."""

from src.cluster_rule import apply_abstention_ceiling
from src.methods.base import FloodMethod


class AbstainingMethod(FloodMethod):
    """Runs `base`, then abstains (predicts no flood) if the predicted region's mean VV >= ceiling."""

    def __init__(self, base, ceiling_db):
        self.base, self.ceiling_db = base, float(ceiling_db)
        self.name = f"{base.name}+guard{self.ceiling_db:g}dB"

    def predict(self, vv, vh, cache_key=None):
        return apply_abstention_ceiling(self.base.predict(vv, vh, cache_key), vv, self.ceiling_db)
