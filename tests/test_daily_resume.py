import datetime
from pathlib import Path

import pytest

import main
import sheets


class Clock(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 16, 8, 0, tzinfo=main.LIMA).astimezone(tz) if tz else cls(2026, 10, 16, 8, 0)


def setup(monkeypatch):
    monkeypatch.setenv('SHEET_ID', 'history-only')
    monkeypatch.delenv('SOLO_LISTA', raising=False)
    monkeypatch.setenv('SHARD', 'all')
    monkeypatch.setattr(main.datetime, 'datetime', Clock)
    monkeypatch.setattr(main, 'seconds_to_deadline', lambda: 14400)
    monkeypatch.setattr(main.time, 'sleep', lambda _: None)
    monkeypatch.setattr(main, 'read_seguimiento', lambda *_: [])


def test_resume_skips_already_ingested_domains_before_browser(monkeypatch):
    setup(monkeypatch)
    stores = [{'dominio': 'done.com', 'tienda': 'Done'}, {'dominio': 'pending.com', 'tienda': 'Pending'}]
    monkeypatch.setattr(main, 'read_base_stores', lambda *_: stores)
    monkeypatch.setattr(main, 'ingesta_existing', lambda *_: {('2026-10-16', 'done.com')})
    reads, writes = [], []
    monkeypatch.setattr(main, 'read_domain', lambda domain, **kw: reads.append(domain) or {'status': 'ready', '_reported_value': 42, '_count_text': '42 results'})
    monkeypatch.setattr(main, 'append_history', lambda *_: None)
    monkeypatch.setattr(main, 'append_ingesta', lambda *args, **kw: writes.append((args, kw)))
    assert main.run_stores() == 0
    assert reads == ['pending.com']
    assert writes[0][1]['count_text'] == '42 results'


def test_personal_followup_remains_history_only(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(main, 'read_base_stores', lambda *_: [])
    monkeypatch.setattr(main, 'read_seguimiento', lambda *_: [{'dominio': 'personal.com', 'tienda': 'Personal'}])
    monkeypatch.setattr(main, 'ingesta_existing', lambda *_: set())
    history, ingesta = [], []
    monkeypatch.setattr(main, 'read_domain', lambda domain, **kw: {'status': 'ready', '_reported_value': 3, '_count_text': '3 results'})
    monkeypatch.setattr(main, 'append_history', lambda *args: history.append(args))
    monkeypatch.setattr(main, 'append_ingesta', lambda *args, **kw: ingesta.append(args))
    assert main.run_stores() == 0
    assert len(history) == 1
    assert ingesta == []


@pytest.mark.parametrize('domain,expected_ingesta', [
    ('active.com', ['active.com']),
    ('info.doutornature.com', []),
])
def test_active_store_in_personal_followup_keeps_its_ingesta_policy(monkeypatch, domain, expected_ingesta):
    setup(monkeypatch)
    monkeypatch.setattr(main, 'read_base_stores', lambda *_: [{'dominio': domain, 'tienda': 'Active'}])
    monkeypatch.setattr(main, 'read_seguimiento', lambda *_: [{'dominio': domain, 'tienda': 'Personal'}])
    monkeypatch.setattr(main, 'ingesta_existing', lambda *_: set())
    reads, history, ingesta = [], [], []
    monkeypatch.setattr(main, 'read_domain', lambda domain, **kw: reads.append(domain) or {'status': 'ready', '_reported_value': 3, '_count_text': '3 results'})
    monkeypatch.setattr(main, 'append_history', lambda _, records: history.extend(records))
    monkeypatch.setattr(main, 'append_ingesta', lambda *args, **kw: ingesta.append(args[3]))
    assert main.run_stores() == 0
    assert reads == [domain]
    assert history == [['2026-10-16', 'Active', domain, 3, 'OK']]
    assert ingesta == expected_ingesta


def test_solo_lista_never_opens_chrome_or_appends_history(monkeypatch, capsys):
    setup(monkeypatch)
    monkeypatch.setenv('SOLO_LISTA', '1')
    monkeypatch.setattr(main, 'read_base_stores', lambda *_: [{'dominio': 'listed.com', 'tienda': 'Listed'}])
    monkeypatch.setattr(main, 'ingesta_existing', lambda *_: set())
    def forbidden(*args, **kwargs): raise AssertionError('No browser or write in list mode')
    monkeypatch.setattr(main, 'read_domain', forbidden)
    monkeypatch.setattr(main, 'append_history', forbidden)
    assert main.run_stores() == 0
    assert 'SOLO_LISTA' in capsys.readouterr().out


def test_base_reader_keeps_upstream_region_order():
    rows = [['dominio', 'tienda', 'region', 'decision', 'estado'],
            ['peru.com', 'Peru', 'PERU', 'SI', 'Activa'],
            ['latam.com', 'Latam', 'LATAM', 'SÍ', 'Activa'],
            ['usa.com', 'USA', 'USA/EU', 'SI', 'Activa']]
    assert [s['dominio'] for s in sheets.parse_base_stores(rows)] == ['usa.com', 'latam.com', 'peru.com']


def test_manual_list_and_shards_and_catalog_separation_are_preserved():
    root = Path(__file__).resolve().parents[1]
    daily = (root / '.github/workflows/daily.yml').read_text()
    assert 'solo_lista:' in daily and 'shard:' in daily
    assert 'group: minisniper-ads' in daily
    assert 'timeout-minutes: 270' in daily
    assert 'cron: "30 12 * * *"' in daily
    catalog = (root / '.github/workflows/catalogo.yml').read_text()
    assert 'schedule:' not in catalog
    assert 'workflow_dispatch:' in catalog
