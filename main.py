"""Una corrida diaria desde Base unica/Tiendas; termina a las 20:00 Lima (DAILY_HASTA)."""
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
    return max(0, (now.replace(hour=int(os.environ.get('DAILY_HASTA') or 20), minute=0, second=0, microsecond=0) - now).total_seconds())


class DailyDeadline(Exception):
    pass


def _deadline(signum, frame):
    raise DailyDeadline()


def run():
    if os.environ.get("SOLO_LISTA"):
        return run_stores()
    remaining = seconds_to_deadline()
    if remaining <= 0:
        os.environ["PENDING_ONLY"] = "1"
        pending = run_stores()
        if pending:
            print(f"FALLO: ya son las 12:00 Lima y quedan {pending} tiendas sin leer hoy.", flush=True)
            return 4
        print("Fin: ya son las 12:00 Lima y no quedaba nada pendiente.", flush=True)
        return 0
    signal.signal(signal.SIGALRM, _deadline)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        return run_stores()
    except DailyDeadline:
        print("Fin duro: 12:00 Lima; historial conservado.", flush=True)
        os.environ["PENDING_ONLY"] = "1"
        signal.setitimer(signal.ITIMER_REAL, 0)
        pending = run_stores()
        if pending:
            print(f"FALLO: fin duro 12:00 Lima con {pending} tiendas sin leer hoy.", flush=True)
            return 4
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
    nshards = int(os.environ.get("NSHARDS") or 4)
    if shard != "all" and not (shard.isdigit() and int(shard) < nshards):
        raise ValueError("INVALID_SHARD")
    if shard != "all":
        stores = [store for index, store in enumerate(stores) if index % nshards == int(shard)]
    today = datetime.datetime.now(LIMA).date().isoformat()
    stores = [store for store in stores if (today, store["dominio"]) not in existing]
    if os.environ.get("PENDING_ONLY"):
        return len(stores)
    followup = read_seguimiento(history_id, today) if shard in {"all", "0"} else []
    domains = {store["dominio"] for store in stores}
    stores += [store for store in followup if store["dominio"] not in domains]
    if os.environ.get("SOLO_LISTA"):
        print("SOLO_LISTA", len(stores), [store["dominio"] for store in stores], flush=True)
        return 0
    print(f"Robot {shard}: {len(stores)} tiendas pendientes desde Base unica/Tiendas y seguimiento personal", flush=True)
    nones = 0
    zero_streak = 0
    for index, store in enumerate(stores):
        if index:
            if seconds_to_deadline() <= PAUSE + 120: break
            time.sleep(PAUSE)
        if seconds_to_deadline() <= 120: break
        result = read_domain(store["dominio"], include_count_text=True)
        value = result.get("_reported_value")
        state = "OK" if result["status"] == "ready" else result["error_code"]
        if value == 0 and not result.get("_zero_clean_confirmed"):
            value, state = None, "ZERO_UNCONFIRMED"  # cero sin doble check anonimo: NONE, nunca 0
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
        # Facebook puede devolver vacio en serie (ceros falsos): 4 ceros sin confirmar seguidos = parar en rojo.
        zero_streak = zero_streak + 1 if state == "ZERO_UNCONFIRMED" else 0
        if zero_streak >= 4:
            print("ALERTA: 4 'No ads match' seguidos; posible respuesta vacia de Facebook. Fin en rojo.", flush=True)
            return 4
    return 3 if nones > max_none else 0


if __name__ == "__main__":
    raise SystemExit(run())
