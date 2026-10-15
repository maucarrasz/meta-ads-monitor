"""Una corrida diaria desde Base unica/Tiendas; termina a las 12:00 Lima."""
import datetime
import os
import signal
import time

from ads_worker import read_domain
from sheets import read_base_stores, read_seguimiento, append_history, ingesta_existing, append_ingesta

BASE_ID = "1cfilechpzK22smRSAz2XatjWwkNX-y70ojc1UMifE8w"
LIMA = datetime.timezone(datetime.timedelta(hours=-5))
PAUSE = 240
NO_INGESTA = {"info.doutornature.com"}


def seconds_to_deadline(now=None):
    now = (now or datetime.datetime.now(LIMA)).astimezone(LIMA)
    return max(0, (now.replace(hour=12, minute=0, second=0, microsecond=0) - now).total_seconds())


class DailyDeadline(Exception):
    pass


def _deadline(signum, frame):
    raise DailyDeadline()


def run():
    if os.environ.get("SOLO_LISTA"):
        return run_stores()
    remaining = seconds_to_deadline()
    if remaining <= 0:
        print("Fin: ya son las 12:00 Lima.", flush=True)
        return 0
    signal.signal(signal.SIGALRM, _deadline)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        return run_stores()
    except DailyDeadline:
        print("Fin duro: 12:00 Lima; historial conservado.", flush=True)
        return 0
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def run_stores():
    history_id = os.environ["SHEET_ID"]
    limit = int(os.environ.get("MAX_STORES", "500"))
    max_none = int(os.environ.get("MAX_NONE", "5"))
    tab = os.environ.get("INGESTA_TAB", "Ingesta_Diaria")
    stores = read_base_stores(BASE_ID, limit)
    existing = ingesta_existing(BASE_ID, tab)
    shard = os.environ.get("SHARD", "all")
    if shard not in {"all", "0", "1", "2", "3"}:
        raise ValueError("INVALID_SHARD")
    if shard != "all":
        stores = [store for index, store in enumerate(stores) if index % 4 == int(shard)]
    today = datetime.datetime.now(LIMA).date().isoformat()
    stores = [store for store in stores if (today, store["dominio"]) not in existing]
    followup = read_seguimiento(history_id, today) if shard in {"all", "0"} else []
    domains = {store["dominio"] for store in stores}
    stores += [store for store in followup if store["dominio"] not in domains]
    if os.environ.get("SOLO_LISTA"):
        print("SOLO_LISTA", len(stores), [store["dominio"] for store in stores], flush=True)
        return 0
    print(f"Robot {shard}: {len(stores)} tiendas pendientes desde Base unica/Tiendas y seguimiento personal", flush=True)
    nones = 0
    for index, store in enumerate(stores):
        if index:
            if seconds_to_deadline() <= PAUSE + 120: break
            time.sleep(PAUSE)
        if seconds_to_deadline() <= 120: break
        result = read_domain(store["dominio"], include_count_text=True)
        value = result.get("_reported_value")
        state = "OK" if result["status"] == "ready" else result["error_code"]
        now = datetime.datetime.now(LIMA)
        record = [now.date().isoformat(), store["tienda"], store["dominio"], value if value is not None else "NONE", state]
        append_history(history_id, [record])
        print(record, flush=True)
        if (value is not None and store["dominio"] in domains
                and store["dominio"] not in NO_INGESTA and (record[0], store["dominio"]) not in existing):
            append_ingesta(BASE_ID, tab, record[0], store["dominio"], store["tienda"], value, now.isoformat(timespec="seconds"), count_text=result.get("_count_text"))
            existing.add((record[0], store["dominio"]))
        if state in {"LOGIN_REQUIRED", "BLOCKED"}:
            print("Meta requiere login o bloqueo; fin sin reintentos.", flush=True)
            return 2
        if value is None: nones += 1
    return 3 if nones > max_none else 0


if __name__ == "__main__":
    raise SystemExit(run())
