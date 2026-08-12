"""WS shard planning helpers for activity metric qualification runners."""
from __future__ import annotations

from typing import Any


class ShardedPublicTradeWS:
  def plan_shards(self, symbols: list[str], *, shard_size: int = 48) -> dict[str, Any]:
      shards = []
      for i in range(0, len(symbols), shard_size):
          chunk = symbols[i : i + shard_size]
          shards.append({"shard_id": i // shard_size, "symbols": chunk, "count": len(chunk)})
      return {"shards": shards, "shard_count": len(shards), "symbols": len(symbols)}


def run_ws_breadth_probe(symbols: list[str], *, duration_sec: float = 30.0) -> dict[str, Any]:
    _ = duration_sec
    return {
        "symbols": len(symbols),
        "symbols_receiving_live_events": 0,
        "shards": [{"events_per_symbol_sample": {}}],
        "probe_mode": "stub_no_ws_in_production_autonomy",
    }
