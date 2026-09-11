from backend.merchants import normalize_merchant, register_merchant_functions


def test_normalize_strips_city_not_upi():
    assert normalize_merchant("UPI-Village Naturals i sro") == "UPI-VILLAGE NATURALS"
    assert normalize_merchant("VILLAGE NATURALS BANGALORE") == "VILLAGE NATURALS"
    assert normalize_merchant("VILLAGE NATURALS BANGALORE IN") == "VILLAGE NATURALS"


def test_normalize_keeps_international_merchant_core():
    assert normalize_merchant("GITHUB INC SAN FRANCISCO US*") == "GITHUB INC SAN FRANCISCO"


def test_normalize_keeps_upi_prefix():
    assert normalize_merchant("UPI-Dominos Pizza") == "UPI-DOMINOS PIZZA"


def test_register_merchant_functions_idempotent_on_file_db(tmp_path):
    from backend.database import connect
    from backend.merchants import register_merchant_functions

    db = tmp_path / "t.duckdb"
    c1 = connect(db)
    c1.close()
    c2 = connect(db)
    register_merchant_functions(c2)
    register_merchant_functions(c2)
    c2.execute("SELECT normalize_merchant('VILLAGE NATURALS BANGALORE IN')").fetchone()
    c2.close()
