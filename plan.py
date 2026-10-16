"""Calcula solo cuantos workers hacen falta: ceil(tiendas activas / capacidad por worker por dia)."""
import json, math, os
from sheets import read_base_stores

BASE_ID = "1cfilechpzK22smRSAz2XatjWwkNX-y70ojc1UMifE8w"
CAPACITY = int(os.environ.get("WORKER_CAPACITY", "55"))   # tiendas por worker (4 min 10 s c/u en un job de 270 min)
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "20"))    # tope de jobs en paralelo en GitHub Free

stores = read_base_stores(BASE_ID, None)
n = len(stores)
need = max(1, math.ceil(n / CAPACITY))
workers = min(need, MAX_WORKERS)
shards = ["all"] if workers == 1 else [str(i) for i in range(workers)]
print(f"PLAN tiendas_activas={n} capacidad_por_worker={CAPACITY} workers_necesarios={need} workers={workers}", flush=True)
with open(os.environ["GITHUB_OUTPUT"], "a") as f:
    f.write(f"shards={json.dumps(shards)}\nnshards={workers}\nneed={need}\nactive={n}\n")
if need > MAX_WORKERS:
    extra = need - MAX_WORKERS
    print(f"FALTAN_WORKERS: hacen falta {extra} workers mas ({extra * CAPACITY} tiendas sin cubrir con {MAX_WORKERS} workers).", flush=True)
    raise SystemExit(5)
