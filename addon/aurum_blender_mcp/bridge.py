"""The socket bridge: a small TCP server that lets an agent drive Blender.

## Why a socket and not a pipe

An MCP server is a separate process, started and stopped by whatever client is
driving the agent, and it has to talk to a Blender that is already open with
somebody's work in it. A socket is the only thing that fits that shape: the
add-on listens once when Blender starts, and any number of clients can come and
go without touching the session.

## Why the work happens on the main thread

`bpy` is not thread-safe, and a socket accept loop is a thread. Every command
that touches the file therefore goes through a queue that the main thread drains
— from a `bpy.app.timers` callback in the GUI, or from an explicit pump loop
when Blender is running with `--background` and has no event loop to hang a
timer on.

The queue is bounded and rejects rather than grows. A client that sends faster
than Blender can draw is a client that will never see its answers anyway, and an
unbounded queue turns that into a machine with no memory left.

## Security

Loopback only, and that is a deliberate limit rather than a default: a socket
that runs arbitrary Python in somebody's open Blender must not be reachable from
the network. The optional token is a second lock, for a machine with several
users on it.
"""

import json
import os
import queue
import socket
import threading
import traceback

try:
    import bpy
except ImportError:  # pragma: no cover - only true outside Blender
    bpy = None


MAX_QUEUED = 32
RECV_BUFFER = 65536


class Context:
    """What a command is allowed to know about the bridge.

    Carries the request's arguments as well as the bridge's settings, because
    several handlers take their target from whichever of the two is present:
    an explicit list of names, or whatever the user has selected in the UI.
    Passing the arguments separately from the context made that impossible and
    the helper reached for something that was not there.
    """

    def __init__(self, port, root, token, arguments=None):
        self.port = port
        self.root = root
        self.token = token
        self.arguments = arguments or {}


class Bridge:
    def __init__(self):
        self.port = 0
        self.root = None
        self.token = None
        self.running = False
        self.requests_served = 0
        self.last_error = None
        self._socket = None
        self._thread = None
        self._clients = []
        self._lock = threading.Lock()
        self._queue = queue.Queue(maxsize=MAX_QUEUED)
        self._timer_registered = False

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self, port, token=None, root=None):
        if self.running:
            return self.info()
        self.token = token or None
        self.root = root or None
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bound to loopback explicitly, not to INADDR_ANY: this socket runs
        # arbitrary Python in an open document.
        self._socket.bind(("127.0.0.1", port))
        self._socket.listen(4)
        self._socket.settimeout(0.5)
        self.port = self._socket.getsockname()[1]
        self.running = True

        self._thread = threading.Thread(target=self._accept_loop, name="aurum-blender-mcp", daemon=True)
        self._thread.start()

        if bpy is not None and not bpy.app.background:
            bpy.app.timers.register(self._tick, first_interval=0.05, persistent=True)
            self._timer_registered = True
        return self.info()

    def stop(self):
        self.running = False
        if self._timer_registered and bpy is not None:
            try:
                bpy.app.timers.unregister(self._tick)
            except ValueError:
                pass
            self._timer_registered = False
        with self._lock:
            clients, self._clients = self._clients, []
        for client in clients:
            _close(client)
        if self._socket is not None:
            _close(self._socket)
            self._socket = None
        self.port = 0
        return self.info()

    def info(self):
        return {
            "running": self.running,
            "port": self.port,
            "root": self.root,
            "token_required": bool(self.token),
            "requests_served": self.requests_served,
            "last_error": self.last_error,
            "queued": self._queue.qsize(),
        }

    # ── the accept thread ────────────────────────────────────────────────────

    def _accept_loop(self):
        while self.running:
            try:
                client, _ = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                if len(self._clients) >= 4:
                    _close(client)
                    continue
                self._clients.append(client)
            threading.Thread(target=self._read_loop, args=(client,), daemon=True).start()

    def _read_loop(self, client):
        buffer = b""
        try:
            while self.running:
                try:
                    chunk = client.recv(RECV_BUFFER)
                except OSError:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        request = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError) as error:
                        _send(client, {"id": None, "ok": False, "error": f"malformed request: {error}"})
                        continue
                    self._enqueue(client, request)
        finally:
            with self._lock:
                if client in self._clients:
                    self._clients.remove(client)
            _close(client)

    def _enqueue(self, client, request):
        try:
            self._queue.put_nowait((client, request))
        except queue.Full:
            _send(
                client,
                {
                    "id": request.get("id"),
                    "ok": False,
                    "error": "Blender is behind on requests; try again in a moment",
                },
            )

    # ── the main thread ──────────────────────────────────────────────────────

    def _tick(self):
        self.pump(limit=8)
        return 0.05 if self.running else None

    def pump(self, limit=None):
        """Run queued commands. Must be called from Blender's main thread."""
        from . import commands

        served = 0
        while limit is None or served < limit:
            try:
                client, request = self._queue.get_nowait()
            except queue.Empty:
                break
            served += 1
            _send(client, self.dispatch(commands, request))
        return served

    def serve_forever(self, poll=0.05):
        """Drive the queue until interrupted.

        For `blender --background`, where there is no event loop to hang a timer
        on and nothing else to do. A script that starts the bridge this way owns
        the process, which is exactly the case for a headless modelling session.
        """
        import time

        try:
            while self.running:
                if self.pump() == 0:
                    time.sleep(poll)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def dispatch(self, commands, request):
        identifier = request.get("id")
        name = request.get("command")
        arguments = request.get("arguments") or {}

        if not isinstance(arguments, dict):
            return {"id": identifier, "ok": False, "error": "'arguments' must be an object"}

        if self.token and arguments.pop("__token__", None) != self.token:
            self.last_error = "rejected a request with a missing or wrong token"
            return {"id": identifier, "ok": False, "error": "unauthorised"}

        handler = commands.COMMANDS.get(name)
        if handler is None:
            return {
                "id": identifier,
                "ok": False,
                "error": f"unknown command {name!r}",
                "available": sorted(commands.COMMANDS),
            }

        context = Context(self.port, self.root, self.token, arguments)
        try:
            result = handler(context, arguments)
        except commands.CommandError as error:
            self.last_error = str(error)
            return {"id": identifier, "ok": False, "error": str(error), "kind": "refused"}
        except Exception:
            self.last_error = traceback.format_exc(limit=6)
            return {
                "id": identifier,
                "ok": False,
                "error": self.last_error,
                "kind": "failed",
            }

        self.requests_served += 1
        self.last_error = None
        return {"id": identifier, "ok": True, "result": result}


def _send(client, payload):
    try:
        client.sendall((json.dumps(payload, default=str) + "\n").encode("utf-8"))
    except OSError:
        pass


def _close(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass
