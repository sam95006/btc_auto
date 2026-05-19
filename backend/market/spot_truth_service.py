from __future__ import annotations

from typing import Dict, Iterable, List


def _safe_float(value) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


class SpotTruthService:
    def __init__(
        self,
        truth_mode: str = "stable_only",
        truth_stable_assets: Iterable[str] | None = None,
        visible_holdings: Iterable[str] | None = None,
        allowed_assets: Iterable[str] | None = None,
    ) -> None:
        self.truth_mode = str(truth_mode or "stable_only").lower()
        self.truth_stable_assets = tuple(truth_stable_assets or ("USDT", "USDC"))
        self.visible_holdings = tuple(visible_holdings or ("BTC", "ETH", "SOL", "BNB"))
        self.allowed_assets = tuple(asset.upper() for asset in (allowed_assets or ()))

    def build_view(self, balances: Dict[str, Dict[str, float]], prices: Dict[str, Dict[str, float]]) -> Dict[str, object]:
        original_assets = set(str(asset).upper() for asset in (balances or {}).keys())
        balances = {
            str(asset).upper(): payload
            for asset, payload in (balances or {}).items()
            if not self.allowed_assets or str(asset).upper() in self.allowed_assets
        }
        truth_assets: List[dict] = []
        stable_total = 0.0
        stable_free = 0.0
        for asset in self.truth_stable_assets:
            payload = balances.get(asset, {}) or {}
            free = _safe_float(payload.get("free"))
            locked = _safe_float(payload.get("locked"))
            total = free + locked
            if not total and not free:
                continue
            stable_total += total
            stable_free += free
            truth_assets.append(
                {
                    "asset": asset,
                    "free": round(free, 8),
                    "locked": round(locked, 8),
                    "total": round(total, 8),
                    "value_usdt": round(total, 8),
                }
            )

        holdings: List[dict] = []
        holdings_total = 0.0
        for asset in self.visible_holdings:
            payload = balances.get(asset, {}) or {}
            quantity = _safe_float(payload.get("free")) + _safe_float(payload.get("locked"))
            price = _safe_float((prices.get(asset) or {}).get("price"))
            value = quantity * price
            holdings_total += value
            holdings.append(
                {
                    "asset": asset,
                    "quantity": round(quantity, 8),
                    "price": round(price, 8),
                    "value": round(value, 8),
                }
            )

        if self.truth_mode == "full_visible_holdings":
            spot_total = stable_total + holdings_total
        else:
            spot_total = stable_total

        excluded_assets = sorted(asset for asset in (original_assets - set(balances.keys())))

        return {
            "truth_mode": self.truth_mode,
            "truth_assets": truth_assets,
            "stable_total": round(stable_total, 8),
            "stable_free": round(stable_free, 8),
            "spot_total": round(spot_total, 8),
            "visible_holdings": holdings,
            "visible_holdings_total": round(holdings_total, 8),
            "allowed_assets": list(self.allowed_assets),
            "excluded_assets_count": 0 if not self.allowed_assets else len(excluded_assets),
            "warning": (
                "spot_truth_is_scoped_to_stable_assets"
                if self.truth_mode == "stable_only"
                else ""
            ),
        }
