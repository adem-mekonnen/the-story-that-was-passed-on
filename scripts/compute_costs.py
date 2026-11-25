"""Parse runs.jsonl and outputs/music/kaggle_runs.jsonl to compute exact telemetry."""

from collections import defaultdict
import json
from pathlib import Path

RUNS_FILE = Path("runs.jsonl")
lines = [json.loads(line) for line in RUNS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]

total_ops = len(lines)
total_hits = sum(1 for e in lines if e.get("cache_hit"))
total_misses = total_ops - total_hits
overall_hit_rate = (total_hits / total_ops * 100) if total_ops else 0
total_latency = sum(float(e.get("latency_seconds", 0.0)) for e in lines)

by_stage = defaultdict(lambda: {"total": 0, "hits": 0, "misses": 0, "latency": 0.0, "cost": 0.0, "providers": set(), "models": set()})
by_provider = defaultdict(lambda: {"total": 0, "hits": 0, "misses": 0, "latency": 0.0, "models": set()})

for e in lines:
    stage = e.get("stage", "unknown")
    prov = e.get("provider", "unknown")
    model = e.get("model", "unknown")
    hit = bool(e.get("cache_hit", False))
    lat = float(e.get("latency_seconds", 0.0))
    cost = float(e.get("cost_usd", 0.0))

    s = by_stage[stage]
    s["total"] += 1
    if hit:
        s["hits"] += 1
    else:
        s["misses"] += 1
    s["latency"] += lat
    s["cost"] += cost
    s["providers"].add(prov)
    s["models"].add(model)

    p = by_provider[prov]
    p["total"] += 1
    if hit:
        p["hits"] += 1
    else:
        p["misses"] += 1
    p["latency"] += lat
    p["models"].add(model)

print(f"Total Operations: {total_ops}")
print(f"Total Cache Hits: {total_hits} ({overall_hit_rate:.1f}%)")
print(f"Total Cold Computes: {total_misses}")
print(f"Cumulative Measured Latency: {total_latency:.2f} seconds ({total_latency / 60:.2f} minutes)")

print("\n--- STAGE BREAKDOWN ---")
for stage in sorted(by_stage.keys()):
    d = by_stage[stage]
    rate = (d["hits"] / d["total"] * 100) if d["total"] else 0
    provs = ", ".join(sorted(d["providers"]))
    models = ", ".join(sorted(d["models"]))
    print(f"{stage:<12} | Total: {d['total']:>3} | Hits: {d['hits']:>3} ({rate:>5.1f}%) | Misses: {d['misses']:>3} | Latency: {d['latency']:>8.2f}s | Providers: [{provs}]")

print("\n--- PROVIDER BREAKDOWN ---")
for prov in sorted(by_provider.keys()):
    d = by_provider[prov]
    rate = (d["hits"] / d["total"] * 100) if d["total"] else 0
    models = ", ".join(sorted(d["models"]))
    print(f"{prov:<15} | Total: {d['total']:>3} | Hits: {d['hits']:>3} ({rate:>5.1f}%) | Misses: {d['misses']:>3} | Latency: {d['latency']:>8.2f}s | Models: [{models}]")

# Inspect Kaggle telemetry if available
kaggle_runs = Path("outputs/music/kaggle_runs.jsonl")
if kaggle_runs.is_file():
    k_lines = [json.loads(l) for l in kaggle_runs.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"\nKaggle Runs Telemetry ({len(k_lines)} entries):")
    for k in k_lines:
        print(f"  - {k.get('run_id')}: {k.get('stage')} | {k.get('model')} | Latency: {k.get('latency_seconds')}s | Status: {k.get('status')}")
