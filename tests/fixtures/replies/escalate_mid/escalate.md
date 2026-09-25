<<<FILE tests/test_add.py
from tiny_pkg import add


def test_add():
    assert add(2, 3) == 5


def test_add_regression_not_subtraction():
    assert add(1, 1) == 2
>>>
