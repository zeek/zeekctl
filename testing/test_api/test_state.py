from __future__ import print_function
from ZeekControl.state import SqliteState

def test_state_basic():
    s = SqliteState(":memory:")

    assert s.get("key") == None
    s.set("key", "value")
    assert s.get("key") == "value"

    s.set("int", 101)
    assert s.get("int") == 101

    s.set("bool", False)
    assert s.get("bool") == False

def test_state_update():
    s = SqliteState(":memory:")

    s.set("key", "value")
    assert s.get("key") == "value"

    s.set("key", "newvalue")
    assert s.get("key") == "newvalue"

def test_state_setdefault():
    s = SqliteState(":memory:")

    s.set("key", "value")
    assert s.get("key") == "value"

    s.setdefault("key", "newvalue")
    assert s.get("key") == "value"

def test_state_items():
    s = SqliteState(":memory:")
    s.set("a", 1)
    s.set("b", "two")

    d = dict(s.items())
    print(d)

    assert d["a"] == 1
    assert d["b"] == "two"
