"""Executable acceptance examples for the proposed access-point boundary."""
import pytest
from access_point_model import Model, Point


@pytest.mark.parametrize("executor", ["device-a", "device-b"])
def test_scan_command_and_passage_are_separate_on_one_or_two_devices(executor):
    model = Model(Point("north", "device-a", executor, executor))
    assert model.scan("s1", "subject-1", "entry", "device-a", 0) == "authorized"
    assert not model.data["inside"]
    assert model.execute("s1", executor, 1)
    assert not model.data["inside"]  # successful command is not a passage
    assert model.passage("p1", "s1", "north", "entry", executor, 2, 2)
    assert model.scan("s2", "subject-1", "exit", "device-a", 30, ready=False) == "authorized"
    assert model.execute("s2", executor, 31)
    assert model.passage("p2", "s2", "north", "exit", executor, 32, 32)
    assert model.data["elapsed"] == {"subject-1": 30}
    assert model.scan("s3", "subject-1", "entry", "device-a", 100) == "authorized"
    assert model.execute("s3", executor, 101)
    assert model.passage("p3", "s3", "north", "entry", executor, 102, 102)
    assert model.data["elapsed"]["subject-1"] == 30  # pause excluded, stay not finalized


@pytest.mark.parametrize("known,ready,device", [(False, True, "a"), (True, False, "a"), (True, True, "other")])
def test_denied_input_never_actuates(known, ready, device):
    m = Model(Point("north", "a", "a", "a"))
    assert m.scan("s", "subject", "entry", device, 0, known=known, ready=ready) == "denied"
    assert not m.execute("s", "a", 1)
    assert not m.data["actuations"] and not m.data["inside"]


def test_replay_restart_and_ambiguous_actuation_do_not_unlock_twice():
    point = Point("north", "a", "b", "b")
    m = Model(point)
    m.scan("s", "subject", "entry", "a", 0)
    assert m.scan("another-scan", "subject", "entry", "a", 1) == "denied"
    assert m.execute("s", "b", 1, lose_reply=True)
    m = Model(point, m.snapshot())
    assert not m.execute("s", "b", 2)
    assert m.scan("s", "subject", "entry", "a", 0) == "attempted"
    assert m.passage("p", "s", "north", "entry", "b", 3, 3)
    assert m.passage("p", "s", "north", "entry", "b", 3, 20)
    assert not m.passage("p-again", "s", "north", "entry", "b", 4, 4)
    assert m.data["actuations"] == 1 and m.data["inside"] == {"subject": 3}
    with pytest.raises(ValueError, match="identity conflict"):
        m.scan("s", "other-subject", "entry", "a", 0)


@pytest.mark.parametrize("failure", ["expiry", "wrong-device", "wrong-point", "wrong-direction", "disable", "restore"])
def test_stale_or_misbound_confirmation_does_not_change_presence(failure):
    m = Model(Point("north", "a", "b", "b"))
    m.scan("s", "subject", "entry", "a", 0)
    m.execute("s", "b", 1)
    if failure == "disable":
        m.disable(); m.enable()
    if failure == "restore":
        m.recover_snapshot()
    assert not m.passage("p", "s", "south" if failure == "wrong-point" else "north",
                         "exit" if failure == "wrong-direction" else "entry",
                         "other" if failure == "wrong-device" else "b", 2,
                         10 if failure == "expiry" else 2)
    assert not m.data["inside"]


def test_offline_expiry_and_scan_only_configuration():
    m = Model(Point("north", "a", "b", "b"))
    m.scan("s", "subject", "entry", "a", 0)
    assert not m.execute("s", "b", 10)  # delayed offline delivery cannot unlock
    assert m.data["actuations"] == 0
    m = Model(Point("desk", "a", None, None, mode="scan"))
    assert m.scan("s", "subject", "entry", "a", 0) == "crossed"
    assert m.scan("e", "subject", "exit", "a", 30) == "crossed"
    assert m.data["elapsed"]["subject"] == 30 and m.data["actuations"] == 0
    with pytest.raises(ValueError, match="not accepted"):
        Point("north", "a", "b", None, mode="blind")


def test_unconfirmed_execution_requires_review_even_after_expiry():
    m = Model(Point("north", "a", "b", "b"))
    m.scan("s", "subject", "entry", "a", 0)
    m.execute("s", "b", 1, lose_reply=True)
    assert m.scan("s2", "subject", "entry", "a", 20) == "denied"
    assert not m.execute("s2", "b", 21)
    assert m.data["actuations"] == 1
