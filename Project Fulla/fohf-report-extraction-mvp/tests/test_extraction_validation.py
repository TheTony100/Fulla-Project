from extraction.performance_table_extractor import _is_valid_return_cell


def test_rejects_fee_style_twenty_percent():
    assert not _is_valid_return_cell("20", "Incentive Fee 20% of profits")
    assert not _is_valid_return_cell("20", "net of all fees (2/20%)")


def test_accepts_table_return():
    assert _is_valid_return_cell("0.72", "2025 2.28 0.99 -1.97 0.51 0.72")
    assert _is_valid_return_cell("-1.97%", "2025 2.28 0.99 -1.97 0.51 0.72")
