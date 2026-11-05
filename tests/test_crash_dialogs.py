"""Read-only crash/message-box detection; all display and sockets are mocked."""
import json
from pathlib import Path
import subprocess
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import call as client
import tm_get_running_pids as discovery


def window(xid, title, width=640, height=240, **extra):
    return dict(xid=xid, name=title, width=width, height=height, **extra)


def test_crash_box_is_distinguished_from_generic_dialog():
    main = window(1, "Trackmania", 1280, 720)
    crash = window(2, 'Crash in "Openplanet.dll"', dialogType=True)
    helper = window(3, "Error", 1, 1)
    assert discovery.classify_dialogs([main, helper]) == []
    result = discovery.classify_dialogs([main, crash, helper])
    assert result[0]["kind"] == "crash"
    assert result[0]["xid"] == 2
    generic = window(4, "Confirmation", dialogType=True, transientFor=1)
    assert discovery.classify_dialogs([main, generic])[0]["kind"] == "message"
    assert discovery.classify_dialogs([main, window(5, "Other window")])[0]["kind"] == "candidate"


def test_timeout_reports_verified_crash_box_and_distinct_exit(capsys):
    dialog = {"xid": 2, "name": "Crash in openplanet.dll", "kind": "crash"}
    with mock.patch.object(sys, "argv", ["call.py", "GetMode"]), \
         mock.patch.object(client, "find_trackmania_pids", return_value=[42]), \
         mock.patch.object(client, "find_game_dialogs", return_value=[dict(dialog, pid=42)]), \
         mock.patch.object(client.socket, "create_connection", side_effect=TimeoutError("timed out")):
        assert client.main() == 10
    result = json.loads(capsys.readouterr().out)
    assert result["dialogs"][0]["kind"] == "crash"
    assert "crash" in result["hint"].lower()


def test_no_display_utilities_never_masks_socket_failure(capsys):
    with mock.patch.object(sys, "argv", ["call.py", "GetMode"]), \
         mock.patch.object(client, "find_trackmania_pids", return_value=[42]), \
         mock.patch.object(discovery.subprocess, "run", side_effect=FileNotFoundError("xdotool")), \
         mock.patch.object(client.socket, "create_connection", side_effect=TimeoutError("timed out")):
        assert client.main() == 4
    result = json.loads(capsys.readouterr().out)
    assert "not" in result["hint"].lower() or "unavailable" in result["hint"].lower()


def test_foreign_windows_are_rejected_before_properties():
    with mock.patch.object(discovery, "_xdotool", return_value="101"), \
         mock.patch.object(discovery, "get_window_pid", return_value=43), \
         mock.patch.object(discovery, "_window_properties") as props:
        assert discovery._x11_windows(42) == []
    props.assert_not_called()
