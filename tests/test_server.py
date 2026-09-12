#!/usr/bin/env python3
"""Tests for the MCP server and the bridge protocol.

    python -m unittest discover -s tests -v

Standard library only, like the code it tests. Nothing here needs Blender: the
server's job is to translate between the Model Context Protocol and a socket,
and the socket can be faked, so the translation is testable on a machine that
has never had Blender on it.

What is *not* covered here is anything that touches `bpy`. Those live in the
add-on and are exercised by driving a real Blender, which no unit test can
stand in for.
"""

import json
import os
import socket
import sys
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(os.path.dirname(HERE), "server")
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

import aurum_blender_mcp as server  # noqa: E402


class FakeBridge:
    """A stand-in for the add-on: same protocol, no Blender."""

    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(2)
        self.socket.settimeout(0.2)
        self.port = self.socket.getsockname()[1]
        self.received = []
        self.reply = {"ok": True, "result": {"fine": True}}
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while self._running:
            try:
                client, _ = self.socket.accept()
            except (socket.timeout, OSError):
                continue
            try:
                buffer = b""
                while b"\n" not in buffer:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    buffer += chunk
                if b"\n" not in buffer:
                    continue
                request = json.loads(buffer.split(b"\n", 1)[0].decode("utf-8"))
                self.received.append(request)
                reply = dict(self.reply)
                reply["id"] = request.get("id")
                client.sendall((json.dumps(reply) + "\n").encode("utf-8"))
            except (OSError, ValueError):
                pass
            finally:
                client.close()

    def stop(self):
        self._running = False
        try:
            self.socket.close()
        except OSError:
            pass


def session(options=None):
    """A session wired to a fake bridge, plus the bridge itself."""
    bridge = FakeBridge()
    parsed = options or server.parse_arguments([])
    parsed.port = bridge.port
    return server.Session(parsed), bridge


class ToolTableTests(unittest.TestCase):
    """The tool table is the contract with every client."""

    def test_every_tool_has_the_shape_mcp_requires(self):
        for tool in server.TOOLS:
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["name"].startswith("blender_"))
                self.assertGreater(len(tool["description"]), 20,
                                   "a description is what the model chooses on")
                schema = tool["inputSchema"]
                self.assertEqual(schema["type"], "object")
                self.assertIn("properties", schema)
                # Every required name must actually be described, or a client
                # generates a call it cannot fill in.
                for name in schema.get("required", []):
                    self.assertIn(name, schema["properties"])

    def test_tool_names_are_unique(self):
        names = [tool["name"] for tool in server.TOOLS]
        self.assertEqual(len(names), len(set(names)), "a duplicate shadows a tool")

    def test_status_can_never_be_withheld(self):
        # The engine's MCP server makes the same promise for the same reason: a
        # client that cannot ask what is wrong cannot tell a refusal from an
        # unreachable server, and will retry forever.
        self.assertIn("blender_status", [tool["name"] for tool in server.TOOLS])


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.session, self.bridge = session()
        self.addCleanup(self.bridge.stop)

    def handle(self, request):
        """Run a request and return what the session wrote to stdout."""
        import io
        import contextlib

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.session.handle(request)
        text = buffer.getvalue().strip()
        return json.loads(text) if text else None

    def test_initialize_negotiates_a_version_the_client_offered(self):
        reply = self.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        })
        self.assertEqual(reply["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(reply["result"]["serverInfo"]["name"], "aurum-blender-mcp")

    def test_initialize_falls_back_rather_than_failing_on_an_unknown_version(self):
        # A client offering a version we have never heard of should still get a
        # session. Refusing would mean the tool is unusable the day a client
        # ships ahead of us, which is the day people try it.
        reply = self.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2099-01-01"},
        })
        self.assertIn(reply["result"]["protocolVersion"], server.PROTOCOL_VERSIONS)

    def test_tools_list_returns_every_tool(self):
        reply = self.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(reply["result"]["tools"]), len(server.TOOLS))

    def test_an_unknown_method_is_an_error_not_a_silent_success(self):
        reply = self.handle({"jsonrpc": "2.0", "id": 3, "method": "nonesuch"})
        self.assertEqual(reply["error"]["code"], -32601)

    def test_an_unknown_tool_reports_which_one(self):
        reply = self.handle({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "blender_nonesuch", "arguments": {}},
        })
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("blender_nonesuch", reply["result"]["content"][0]["text"])

    def test_a_call_reaches_the_bridge_with_the_command_unprefixed(self):
        # The add-on knows nothing about MCP and has no opinion about the
        # "blender_" prefix; that is the server's business.
        self.handle({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "blender_object_create",
                       "arguments": {"type": "CUBE"}},
        })
        self.assertEqual(len(self.bridge.received), 1)
        self.assertEqual(self.bridge.received[0]["command"], "object_create")
        self.assertEqual(self.bridge.received[0]["arguments"]["type"], "CUBE")

    def test_a_notification_gets_no_reply(self):
        reply = self.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(reply, "a notification with a reply confuses the client")

    def test_an_unreachable_blender_says_how_to_reach_one(self):
        # The most common failure by a distance, and the one where a bare
        # "connection refused" wastes the most of somebody's afternoon.
        self.bridge.stop()
        reply = self.handle({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "blender_status", "arguments": {}},
        })
        text = reply["result"]["content"][0]["text"]
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("not listening", text)
        self.assertIn("--launch", text)

    def test_a_port_with_nothing_on_it_is_translated_whatever_the_errno(self):
        # This assertion is why the suite runs on three platforms. A closed port
        # is refused on Windows and reset on Linux, and a Blender that dies
        # mid-call resets on both, so the error can surface at the connect or at
        # the first send. Only the connect was being translated, and Linux CI
        # found the other one.
        closed = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
        closed.close()

        blender = server.Blender(port, None)
        with self.assertRaises(server.BridgeError) as caught:
            blender.call("status", {})
        self.assertIn("not listening", str(caught.exception))
        self.assertIn("--launch", str(caught.exception))


class BridgeReplyTests(unittest.TestCase):
    def setUp(self):
        self.session, self.bridge = session()
        self.addCleanup(self.bridge.stop)

    def test_a_refusal_from_blender_is_reported_as_one(self):
        self.bridge.reply = {"ok": False, "error": "no object named 'hull'",
                             "kind": "refused"}
        outcome = self.session.call_tool(
            {"name": "blender_object_delete", "arguments": {"objects": ["hull"]}}
        )
        self.assertTrue(outcome["isError"])
        self.assertIn("no object named", outcome["content"][0]["text"])

    def test_a_token_is_sent_when_one_is_configured(self):
        parsed = server.parse_arguments([])
        parsed.token = "secret"
        self.session, self.bridge = session(parsed)
        self.session.blender.call("status", {})
        self.assertEqual(self.bridge.received[0]["arguments"]["__token__"], "secret")

    def test_no_token_key_is_sent_when_none_is_configured(self):
        self.session.blender.call("status", {})
        self.assertNotIn("__token__", self.bridge.received[0]["arguments"])


class ArgumentTests(unittest.TestCase):
    def test_defaults_are_usable_with_no_arguments_at_all(self):
        options = server.parse_arguments([])
        self.assertEqual(options.port, server.DEFAULT_PORT)
        self.assertIsNone(options.token)

    def test_environment_variables_stand_in_for_flags(self):
        os.environ["AURUM_BLENDER_PORT"] = "9111"
        os.environ["AURUM_BLENDER_TOKEN"] = "fromenv"
        try:
            options = server.parse_arguments([])
            self.assertEqual(options.port, 9111)
            self.assertEqual(options.token, "fromenv")
        finally:
            del os.environ["AURUM_BLENDER_PORT"]
            del os.environ["AURUM_BLENDER_TOKEN"]

    def test_a_flag_beats_the_environment(self):
        os.environ["AURUM_BLENDER_PORT"] = "9111"
        try:
            options = server.parse_arguments(["--port", "9222"])
            self.assertEqual(options.port, 9222)
        finally:
            del os.environ["AURUM_BLENDER_PORT"]

    def test_find_blender_reports_a_missing_explicit_path(self):
        with self.assertRaises(server.BridgeError):
            server.find_blender(r"A:\definitely\not\here\blender.exe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
