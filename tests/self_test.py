#!/usr/bin/env python3
"""Self-test for the LLs vPlayer remote-control scaffold."""

import http.client
import json
import logging
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import remote_control  # noqa: E402
import mpris_adapter  # noqa: E402


class FakeAdapter:
    connected = True

    def get_status(self):
        return {
            "playback_state": "paused",
            "position_ms": 0,
            "duration_ms": None,
            "loop_mode": "off",
            "volume": 0.5,
            "current_item": None,
            "playlist": {"active": False},
        }

    def play(self):
        return {"playback_state": "playing"}

    def set_loop(self, mode):
        return {"loop_mode": mode}

    def set_volume(self, level):
        return {"volume": level}


class ServerHarness:
    def __init__(self, adapter):
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.token = "self-test-token"
        config = remote_control.Config(
            host="127.0.0.1",
            port=0,
            token=self.token,
            config_path=temp_path / "config.json",
            log_path=temp_path / "remote-control.log",
        )
        logger = logging.getLogger("llv-remote-control-self-test-%s" % id(self))
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        self.server = remote_control.ControlServer(("127.0.0.1", 0), config, adapter, logger)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp_dir.cleanup()

    def request(self, method, path, body=None, token=None):
        headers = {}
        payload = None
        if token is not None:
            headers["Authorization"] = "Bearer %s" % token
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            data = json.loads(response.read().decode("utf-8"))
            return response.status, data
        finally:
            conn.close()


class RemoteControlSelfTest(unittest.TestCase):
    def test_discovery_auth_and_no_adapter(self):
        harness = ServerHarness(remote_control.MissingAdapter())
        try:
            status, body = harness.request("GET", "/discovery")
            self.assertEqual(status, 200)
            self.assertIn("lls.control_url", body)
            self.assertIn("lls.status_url", body)
            self.assertFalse(body["adapter_connected"])

            status, body = harness.request("GET", "/status")
            self.assertEqual(status, 401)
            self.assertEqual(body["error"]["code"], "unauthorized")

            status, body = harness.request("POST", "/control/play", body={}, token=harness.token)
            self.assertEqual(status, 503)
            self.assertEqual(body["error"]["code"], "no_adapter")
        finally:
            harness.close()

    def test_request_validation(self):
        harness = ServerHarness(remote_control.MissingAdapter())
        try:
            status, body = harness.request(
                "POST",
                "/control/seek",
                body={"position_ms": 1, "delta_ms": 1},
                token=harness.token,
            )
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "bad_request")

            status, body = harness.request(
                "POST",
                "/control/seek",
                body={"position_ms": 1.5},
                token=harness.token,
            )
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "bad_request")

            status, body = harness.request(
                "POST",
                "/control/volume",
                body={"level": 2},
                token=harness.token,
            )
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "bad_request")

            status, body = harness.request(
                "POST",
                "/control/volume",
                body={"level": "nan"},
                token=harness.token,
            )
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "bad_request")
        finally:
            harness.close()

    def test_fake_adapter_success(self):
        harness = ServerHarness(FakeAdapter())
        try:
            status, body = harness.request("GET", "/status", token=harness.token)
            self.assertEqual(status, 200)
            self.assertTrue(body["adapter_connected"])
            self.assertEqual(body["status"]["playback_state"], "paused")

            status, body = harness.request("POST", "/control/play", body={}, token=harness.token)
            self.assertEqual(status, 200)
            self.assertEqual(body["result"]["playback_state"], "playing")
        finally:
            harness.close()

    def test_adapter_method_missing_is_honest(self):
        harness = ServerHarness(FakeAdapter())
        try:
            status, body = harness.request("POST", "/control/pause", body={}, token=harness.token)
            self.assertEqual(status, 501)
            self.assertEqual(body["error"]["code"], "adapter_method_missing")
        finally:
            harness.close()

    def test_existing_config_token_is_made_private(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text('{"token": "secret", "host": "127.0.0.1", "port": 8091}\n', encoding="utf-8")
            path.chmod(0o644)
            args = remote_control.build_parser().parse_args(["--config", str(path)])
            config = remote_control.load_config(args)
            self.assertEqual(config.token, "secret")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class MprisAdapterTest(unittest.TestCase):
    def test_status_parses_real_gdbus_value_shapes(self):
        replies = {
            "PlaybackStatus": "(<'Paused'>,)",
            "Position": "(<int64 125000>,)",
            "Metadata": "(<{'xesam:title': <'Sample title'>}>,)",
            "CanPlay": "(<true>,)",
            "CanPause": "(<true>,)",
            "CanSeek": "(<true>,)",
            "CanGoNext": "(<false>,)",
            "CanGoPrevious": "(<false>,)",
            "CanControl": "(<true>,)",
        }

        def run(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, replies[command[-1]] + "\n", "")

        adapter = mpris_adapter.MprisAdapter()
        with mock.patch("mpris_adapter.subprocess.run", side_effect=run):
            status = adapter.get_status()

        self.assertEqual(status["playback_state"], "paused")
        self.assertEqual(status["position_ms"], 125)
        self.assertEqual(status["current_item"]["title"], "Sample title")
        self.assertFalse(status["capabilities"]["next"])
        self.assertEqual(status["unsupported"], ["loop", "volume"])

    def test_loop_and_volume_are_rejected_not_faked(self):
        adapter = mpris_adapter.MprisAdapter()
        with self.assertRaises(remote_control.AdapterError) as loop_error:
            adapter.set_loop("all")
        self.assertEqual(loop_error.exception.code, "unsupported_command")
        self.assertEqual(loop_error.exception.http_status, 501)

        with self.assertRaises(remote_control.AdapterError) as volume_error:
            adapter.set_volume(0.5)
        self.assertEqual(volume_error.exception.code, "unsupported_command")

    def test_missing_mpris_service_is_no_adapter(self):
        adapter = mpris_adapter.MprisAdapter()
        failed = subprocess.CompletedProcess(["gdbus"], 1, "", "GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown")
        with mock.patch("mpris_adapter.subprocess.run", return_value=failed):
            with self.assertRaises(remote_control.AdapterError) as error:
                adapter.get_status()
        self.assertEqual(error.exception.code, "no_adapter")


if __name__ == "__main__":
    unittest.main(verbosity=2)
