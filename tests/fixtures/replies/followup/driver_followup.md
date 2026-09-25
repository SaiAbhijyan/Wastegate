<<<FILE tests/test_regression.py
from tiny_pkg import add


def test_add_negative():
    assert add(-2, 1) == -1
>>>
