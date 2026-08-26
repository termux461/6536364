from app.services.payments.base import kopecks_from_rubles, rubles_from_kopecks


def test_roundtrip_is_exact():
    for kopecks in (1, 99, 100, 150000, 999999):
        assert kopecks_from_rubles(rubles_from_kopecks(kopecks)) == kopecks


def test_no_float_drift():
    assert kopecks_from_rubles("1500.50") == 150050
    assert kopecks_from_rubles(0.1 + 0.2) == 30
    assert rubles_from_kopecks(150000) == "1500.00"
