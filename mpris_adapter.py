#!/usr/bin/env python3
"""MPRIS adapter for the LLs vPlayer remote-control sidecar.

LLs vPlayer 2.0.6 wires MPRIS transport and position signals to the player,
but does not wire MPRIS LoopStatus or Volume property writes to its real
playlist loop mode or media volume.  Those two operations must therefore fail
explicitly instead of reporting a successful but ineffective command.
"""

import re
import subprocess

from remote_control import AdapterError

SERVICE = "org.mpris.MediaPlayer2.llsVplayer"
OBJECT_PATH = "/org/mpris/MediaPlayer2"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
DBUS_IFACE = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
STRING_RE = re.compile(r"\(<\'(?P<value>.*)\'\>,\)$")
INT64_RE = re.compile(r"\(<int64 (?P<value>-?[0-9]+)>\,\)$")
BOOL_RE = re.compile(r"\(<(?P<value>true|false)>\,\)$")
TITLE_RE = re.compile(r"xesam:title': <'(?P<value>[^']*)'>")


class MprisAdapter:
    def __init__(self, _config=None):
        self._config = _config or {}

    @property
    def connected(self):
        try:
            names = self._call(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    DBUS_IFACE,
                    "--object-path",
                    DBUS_PATH,
                    "--method",
                    f"{DBUS_IFACE}.ListNames",
                ]
            )
        except AdapterError:
            return False
        return SERVICE in names

    def get_status(self):
        return {
            "service": SERVICE,
            "playback_state": self._string_property("PlaybackStatus").lower(),
            "position_ms": self._int64_property("Position") // 1000,
            "current_item": {"title": self._metadata_title()},
            "capabilities": {
                "play": self._bool_property("CanPlay"),
                "pause": self._bool_property("CanPause"),
                "seek": self._bool_property("CanSeek"),
                "next": self._bool_property("CanGoNext"),
                "previous": self._bool_property("CanGoPrevious"),
                "control": self._bool_property("CanControl"),
                "stop": True,
                "loop": False,
                "volume": False,
            },
            "unsupported": ["loop", "volume"],
        }

    def play(self):
        return self._player_method("Play")

    def pause(self):
        return self._player_method("Pause")

    def toggle(self):
        return self._player_method("PlayPause")

    def stop(self):
        return self._player_method("Stop")

    def next(self):
        return self._player_method("Next")

    def previous(self):
        return self._player_method("Previous")

    def seek(self, position_ms=None, delta_ms=None):
        if not self._bool_property("CanSeek"):
            raise AdapterError("cannot_seek", "LLs vPlayer reported that seeking is unavailable.", 409)
        if position_ms is not None:
            delta_ms = position_ms - (self._int64_property("Position") // 1000)
        self._player_method("Seek", str(int(delta_ms) * 1000))
        return {"position_ms": int(position_ms) if position_ms is not None else None, "delta_ms": int(delta_ms)}

    def set_loop(self, mode):
        raise AdapterError(
            "unsupported_command",
            "LLs vPlayer 2.0.6 does not apply MPRIS loop changes to its real playlist loop mode.",
            501,
            {"command": "loop", "requested_mode": mode},
        )

    def set_volume(self, level):
        raise AdapterError(
            "unsupported_command",
            "LLs vPlayer 2.0.6 does not apply MPRIS volume changes to its real media volume.",
            501,
            {"command": "volume", "requested_level": level},
        )

    def _property_call(self, name):
        return self._call(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                SERVICE,
                "--object-path",
                OBJECT_PATH,
                "--method",
                f"{PROPERTIES_IFACE}.Get",
                PLAYER_IFACE,
                name,
            ]
        )

    def _string_property(self, name):
        match = STRING_RE.match(self._property_call(name))
        if not match:
            raise AdapterError("bad_adapter_reply", f"Could not parse string property {name}.", 502)
        return match.group("value")

    def _int64_property(self, name):
        match = INT64_RE.match(self._property_call(name))
        if not match:
            raise AdapterError("bad_adapter_reply", f"Could not parse integer property {name}.", 502)
        return int(match.group("value"))

    def _bool_property(self, name):
        match = BOOL_RE.match(self._property_call(name))
        if not match:
            raise AdapterError("bad_adapter_reply", f"Could not parse boolean property {name}.", 502)
        return match.group("value") == "true"

    def _metadata_title(self):
        output = self._property_call("Metadata")
        match = TITLE_RE.search(output)
        return match.group("value") if match else ""

    def _player_method(self, name, *args):
        self._call(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                SERVICE,
                "--object-path",
                OBJECT_PATH,
                "--method",
                f"{PLAYER_IFACE}.{name}",
                *args,
            ]
        )
        return {"method": name.lower()}

    def _call(self, cmd):
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if completed.returncode == 0:
            return completed.stdout.strip()

        message = (completed.stderr or completed.stdout).strip() or "adapter command failed"
        if "ServiceUnknown" in message or "NameHasNoOwner" in message or SERVICE in message:
            raise AdapterError(
                "no_adapter",
                "LLs vPlayer is not running or is not exporting its MPRIS control surface.",
                503,
                {"service": SERVICE},
            )
        raise AdapterError(
            "adapter_failure",
            "The MPRIS adapter command failed.",
            502,
            {"command": cmd[0], "details": message},
        )


def create_adapter(config):
    return MprisAdapter(config)
