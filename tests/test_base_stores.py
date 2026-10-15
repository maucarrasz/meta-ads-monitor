import importlib
import pytest


def test_base_headers_and_decisions_are_authoritative():
    sheets = importlib.import_module("sheets")
    rows = [
        ["Estado", "Decisión", "Dominio", "Tienda"],
        ["Activa", "SÍ", "https://www.example.com/path", "Example"],
        ["Descartado", "SI", "discarded.com", "Discarded"],
        ["Activa", "NO", "inactive.com", "Inactive"],
        ["Seguimiento", "si", "another.com", "Another"],
    ]
    assert sheets.parse_base_stores(rows) == [
        {"dominio": "example.com", "tienda": "Example"},
        {"dominio": "another.com", "tienda": "Another"},
    ]


def test_conflicting_duplicate_is_not_active():
    sheets = importlib.import_module("sheets")
    rows = [["dominio", "decision"], ["example.com", "SI"], ["example.com", "NO"]]
    assert sheets.parse_base_stores(rows) == []


def test_missing_headers_fail_closed():
    import pytest
    sheets = importlib.import_module("sheets")
    with pytest.raises(ValueError, match="TIENDAS_HEADER_MISSING"):
        sheets.parse_base_stores([["dominio", "activo"], ["example.com", "SI"]])


def test_daily_deadline_is_noon_lima():
    import datetime
    main = importlib.import_module("main")
    assert main.seconds_to_deadline(datetime.datetime(2026, 10, 15, 16, 59, tzinfo=datetime.timezone.utc)) == 60
    assert main.seconds_to_deadline(datetime.datetime(2026, 10, 15, 17, 0, tzinfo=datetime.timezone.utc)) == 0
    assert main.seconds_to_deadline(datetime.datetime(2026, 10, 15, 18, 0, tzinfo=datetime.timezone.utc)) == 0


@pytest.mark.parametrize('count,literal', [(42, '42 results'), (1234, '~1,234 results'),
                                         (0, '0 results'), (0, 'No ads match your search criteria')])
def test_ingesta_preserves_real_literal_including_exact_non_estimate(monkeypatch, count, literal):
    sheets = importlib.import_module('sheets')
    writes = []
    class Service:
        def values(self): return self
        def append(self, **kwargs):
            writes.append(kwargs['body']['values'][0])
            return self
        def execute(self): return {}
    monkeypatch.setattr(sheets, '_svc', lambda: Service())
    sheets.append_ingesta('base', 'Ingesta_Diaria', '2026-10-15', 'example.com', 'Example', count,
                         '2026-10-15T07:30:00-05:00', count_text=literal)
    assert writes[0][4] == literal


def test_missing_count_text_never_generates_a_receipt(monkeypatch):
    sheets = importlib.import_module('sheets')
    monkeypatch.setattr(sheets, '_svc', lambda: pytest.fail('No Sheets write'))
    with pytest.raises(ValueError, match='MISSING_META_COUNT_TEXT'):
        sheets.append_ingesta('base', 'Ingesta_Diaria', '2026-10-15', 'example.com', 'Example', 0,
                             '2026-10-15T07:30:00-05:00', count_text=None)
