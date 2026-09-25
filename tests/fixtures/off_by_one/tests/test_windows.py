from windows import sliding_windows


def test_includes_last_window():
    assert sliding_windows([1, 2, 3], 2) == [[1, 2], [2, 3]]


def test_whole_list_is_one_window():
    assert sliding_windows([1, 2, 3], 3) == [[1, 2, 3]]
