#!/usr/bin/env python3
"""Aurum Blender MCP — the Model Context Protocol server for Blender.

Any MCP client can run this: Codex, Claude Code, Cursor, VS Code, or an agent
framework of your own. It speaks newline-delimited JSON-RPC 2.0 on stdin and
stdout, which is the MCP stdio transport, and forwards each tool call to the
Aurum Blender MCP add-on over a loopback socket.

    python aurum_blender_mcp.py
    python aurum_blender_mcp.py --port 9081 --token secret --root A:/project

## Why the add-on is separate

Blender's Python is the only interpreter that can touch `bpy`, and it is
embedded in Blender. So the add-on has to live inside Blender and this has to
live outside it, and the socket between them is the seam. That seam is also what
makes the pair client-agnostic: nothing above it knows what an MCP client is,
and nothing below it knows what a mesh is.

## No dependencies

Standard library only. An MCP server is the first thing somebody runs when they
try a tool out, and it should not be able to fail because a package index was
unreachable or a virtual environment went stale.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PORT = 9081
SOCKET_TIMEOUT = 120.0


class BridgeError(Exception):
    """The add-on could not be reached, or refused the command."""


def unreachable(error, host="127.0.0.1", port=None) -> str:
    """What to say when the socket to Blender did not work.

    One message for every way that happens, because from where the agent is
    standing they are the same fact: there is no Blender to talk to. Which
    errno it was is our problem, not theirs.
    """
    where = f"{host}:{port}" if port else host
    return (
        f"Blender is not listening on {where} ({error}). "
        "Open Blender with the Aurum Blender MCP add-on enabled and press "
        "Start Bridge, or run this server with --launch to start one."
    )


# ── talking to Blender ───────────────────────────────────────────────────────


class Blender:
    def __init__(self, port, token, host="127.0.0.1"):
        self.host = host
        self.port = port
        self.token = token

    def call(self, command, arguments=None):
        payload = {"id": 1, "command": command, "arguments": dict(arguments or {})}
        if self.token:
            payload["arguments"]["__token__"] = self.token

        try:
            connection = socket.create_connection((self.host, self.port), timeout=SOCKET_TIMEOUT)
        except OSError as error:
            raise BridgeError(unreachable(error)) from error

        try:
            connection.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            buffer = b""
            while b"\n" not in buffer:
                chunk = connection.recv(65536)
                if not chunk:
                    raise BridgeError("Blender closed the connection before answering")
                buffer += chunk
            reply = json.loads(buffer.split(b"\n", 1)[0].decode("utf-8"))
        except OSError as error:
            # The same failure, one step later. A port with nothing on it is
            # refused on Windows and reset on Linux, and a Blender that dies
            # mid-call resets on both -- so the connection error can surface at
            # the connect or at the first send, and only the first of those was
            # being translated. A raw traceback here is the least useful thing
            # to hand somebody whose Blender has just gone away.
            raise BridgeError(unreachable(error)) from error
        finally:
            connection.close()

        if not reply.get("ok"):
            raise BridgeError(reply.get("error") or "the command failed")
        return reply.get("result")

    def alive(self):
        try:
            self.call("status")
            return True
        except BridgeError:
            return False


# ── launching Blender ────────────────────────────────────────────────────────


def find_blender(explicit=None):
    """Locate a Blender to launch.

    An explicit path wins, then `PATH`, then the two places a Blender on this
    machine actually lives. A server that can find nothing says so rather than
    starting an arbitrary executable.
    """
    if explicit:
        if not os.path.exists(explicit):
            raise BridgeError(f"no Blender at {explicit}")
        return explicit

    for name in ("blender", "blender.exe"):
        found = shutil.which(name)
        if found:
            return found

    candidates = [
        r"A:\SteamLibrary\steamapps\common\Blender\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/usr/bin/blender",
        "/usr/local/bin/blender",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def launch_blender(port, token, root, explicit=None):
    """Start Blender with the add-on running and the bridge open."""
    executable = find_blender(explicit)
    if executable is None:
        raise BridgeError(
            "no Blender found. Pass --blender <path>, or put Blender on PATH."
        )

    expression = (
        "import bpy, addon_utils;"
        "addon_utils.enable('aurum_blender_mcp', default_set=False, persistent=True);"
        "from aurum_blender_mcp import get_bridge;"
        f"get_bridge().start({port}, {token!r}, {root!r});"
    )
    creation = 0
    if os.name == "nt":
        creation = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    subprocess.Popen(
        [executable, "--python-expr", expression],
        creationflags=creation,
        close_fds=True,
    )
    return executable


def wait_for_bridge(blender, seconds=45.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if blender.alive():
            return True
        time.sleep(0.5)
    return False


# ── the tool table ───────────────────────────────────────────────────────────


def _tool(name, description, properties=None, required=None):
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
        },
    }


VEC3 = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
OBJECTS = {"type": "array", "items": {"type": "string"}}

TOOLS = [
    _tool(
        "blender_status",
        "Whether Blender is reachable, what version it is, and whether the open file has "
        "unsaved changes. Never withheld: an agent that cannot tell a refusal from an "
        "unreachable Blender will retry forever.",
    ),
    _tool(
        "blender_execute",
        "Run Python inside Blender and return what the code binds to `result`. This is the "
        "escape hatch the rest of the tool list is built around: anything not covered by a "
        "named tool is one expression away, with the whole of bpy available.",
        {
            "code": {
                "type": "string",
                "description": "Python source. A single expression is evaluated; anything else is executed.",
            }
        },
        ["code"],
    ),
    _tool("blender_scene_info", "Every object in the scene with its transform and mesh counts."),
    _tool(
        "blender_object_list",
        "Objects in the file, optionally filtered by type.",
        {"type": {"type": "string", "description": "MESH, CAMERA, LIGHT, EMPTY, ..."}},
    ),
    _tool(
        "blender_object_create",
        "Add a primitive. The workhorse for hard-surface blocking: a mech is a great many "
        "boxes and cylinders at exact sizes.",
        {
            "type": {
                "type": "string",
                "enum": ["CUBE", "SPHERE", "CYLINDER", "CONE", "TORUS", "PLANE", "EMPTY", "CAMERA", "LIGHT"],
            },
            "name": {"type": "string"},
            "location": VEC3,
            "rotation": VEC3,
            "scale": VEC3,
            "size": {"type": "number"},
        },
        ["type"],
    ),
    _tool(
        "blender_object_set",
        "Move, rotate, scale, rename, reparent or hide one object.",
        {
            "object": {"type": "string"},
            "location": VEC3,
            "rotation": VEC3,
            "scale": VEC3,
            "name": {"type": "string"},
            "parent": {"type": "string"},
            "visible": {"type": "boolean"},
        },
        ["object"],
    ),
    _tool(
        "blender_object_delete",
        "Delete the named objects, or the current selection.",
        {"objects": OBJECTS},
    ),
    _tool(
        "blender_object_duplicate",
        "Copy objects, optionally offset. The cheap way to build a symmetric or repeated part.",
        {"objects": OBJECTS, "offset": VEC3},
    ),
    _tool(
        "blender_object_join",
        "Join objects into the first one. Do this before export when separate parts are only "
        "separate for modelling.",
        {"objects": OBJECTS},
    ),
    _tool(
        "blender_object_apply_transform",
        "Bake rotation and scale into the mesh data. Worth doing before export so the "
        "exported node transforms are identity and the game code has nothing to undo.",
        {
            "objects": OBJECTS,
            "location": {"type": "boolean"},
            "rotation": {"type": "boolean", "default": True},
            "scale": {"type": "boolean", "default": True},
        },
    ),
    _tool(
        "blender_mesh_from_data",
        "Build a mesh from explicit vertices and faces. More precise than driving the "
        "primitive tools when a shape has to be exact.",
        {
            "name": {"type": "string"},
            "vertices": {"type": "array", "items": VEC3},
            "faces": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "location": VEC3,
            "rotation": VEC3,
        },
        ["vertices", "faces"],
    ),
    _tool(
        "blender_mesh_bevel",
        "Bevel the selected or named meshes. The single change that most makes a box read "
        "as a manufactured part: a real edge catches light, a mathematical one does not.",
        {
            "objects": OBJECTS,
            "width": {"type": "number", "default": 0.02},
            "segments": {"type": "integer", "default": 2},
            "angle": {"type": "number", "default": 30},
            "apply": {"type": "boolean", "default": True},
        },
    ),
    _tool(
        "blender_mesh_boolean",
        "Union, difference or intersect the objects into the first. How panels get cut and "
        "how a hull gets its recesses.",
        {
            "objects": OBJECTS,
            "operation": {"type": "string", "enum": ["UNION", "DIFFERENCE", "INTERSECT"]},
        },
        ["operation"],
    ),
    _tool(
        "blender_mesh_modifier",
        "Add a modifier such as MIRROR, ARRAY, SUBSURF or SOLIDIFY, with settings, "
        "optionally applied.",
        {
            "objects": OBJECTS,
            "modifier": {"type": "string"},
            "settings": {"type": "object"},
            "apply": {"type": "boolean", "default": False},
        },
        ["modifier"],
    ),
    _tool(
        "blender_material_new",
        "Create a Principled material.",
        {
            "name": {"type": "string"},
            "settings": {
                "type": "object",
                "description": "Principled inputs by name: 'Base Color', 'Metallic', 'Roughness', 'Emission Color', 'Emission Strength'.",
            },
        },
        ["name"],
    ),
    _tool(
        "blender_material_set",
        "Change a material's Principled inputs.",
        {"material": {"type": "string"}, "settings": {"type": "object"}},
        ["material", "settings"],
    ),
    _tool(
        "blender_material_assign",
        "Put a material on the selected or named meshes.",
        {"material": {"type": "string"}, "objects": OBJECTS, "slot": {"type": "integer"}},
        ["material"],
    ),
    _tool("blender_material_list", "Every material in the file and its Principled settings."),
    _tool(
        "blender_export_gltf",
        "Export to glTF. GLB by default: one file, which is what a game wants and what a "
        "version control system copes with.",
        {
            "path": {"type": "string"},
            "format": {"type": "string", "enum": ["GLB", "GLTF_SEPARATE", "GLTF_EMBEDDED"]},
            "objects": OBJECTS,
            "apply_modifiers": {"type": "boolean", "default": True},
            "y_up": {"type": "boolean", "default": True},
        },
        ["path"],
    ),
    _tool(
        "blender_import_gltf",
        "Import a glTF file into the current scene.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    _tool(
        "blender_capture",
        "Render a picture of the scene and save it. Rendered rather than screen-grabbed, so "
        "it works with Blender in the background. This is how an agent checks its own work.",
        {
            "name": {"type": "string"},
            "width": {"type": "integer", "default": 960},
            "height": {"type": "integer", "default": 600},
            "engine": {"type": "string"},
            "transparent": {"type": "boolean"},
        },
    ),
    _tool("blender_save", "Save the file, optionally to a new path.", {"path": {"type": "string"}}),
    _tool(
        "blender_open",
        "Open a .blend. Refuses to discard unsaved work unless told to.",
        {"path": {"type": "string"}, "discard_changes": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "blender_new_scene",
        "Start an empty file. Refuses to discard unsaved work unless told to.",
        {"discard_changes": {"type": "boolean"}, "units": {"type": "boolean", "default": True}},
    ),
    _tool(
        "blender_launch",
        "Start Blender with the add-on enabled, if it is not already running. Use this when "
        "blender_status says Blender is unreachable.",
        {"wait_seconds": {"type": "number", "default": 45}},
    ),
]


# ── JSON-RPC ─────────────────────────────────────────────────────────────────


def respond(identifier, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": identifier}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def text_result(text, is_error=False):
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


class Session:
    def __init__(self, options):
        self.options = options
        self.blender = Blender(options.port, options.token)
        self.initialised = False

    def handle(self, request):
        method = request.get("method")
        identifier = request.get("id")
        params = request.get("params") or {}

        # Notifications carry no id and take no reply.
        if identifier is None and method in ("notifications/initialized", "initialized"):
            self.initialised = True
            return
        if method == "initialize":
            wanted = params.get("protocolVersion")
            version = wanted if wanted in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return respond(
                identifier,
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "aurum-blender-mcp", "version": "1.0.0"},
                },
            )
        if method in ("ping",):
            return respond(identifier, {})
        if method == "tools/list":
            return respond(identifier, {"tools": TOOLS})
        if method == "tools/call":
            return respond(identifier, self.call_tool(params))
        return respond(
            identifier,
            error={"code": -32601, "message": f"unknown method {method!r}"},
        )

    def call_tool(self, params):
        name = params.get("name")
        arguments = params.get("arguments") or {}
        known = {tool["name"] for tool in TOOLS}
        if name not in known:
            return text_result(f"unknown tool {name!r}", is_error=True)

        try:
            if name == "blender_launch":
                return self.launch(arguments)
            result = self.blender.call(name.replace("blender_", "", 1), arguments)
        except BridgeError as error:
            return text_result(str(error), is_error=True)
        except Exception as error:  # noqa: BLE001 - reported, never fatal
            return text_result(f"{type(error).__name__}: {error}", is_error=True)

        return text_result(_render(name, result))

    def launch(self, arguments):
        if self.blender.alive():
            return text_result("Blender is already running and listening.")
        root = self.options.root or os.getcwd()
        executable = launch_blender(self.options.port, self.options.token, root, self.options.blender)
        if not wait_for_bridge(self.blender, float(arguments.get("wait_seconds", 45))):
            return text_result(
                f"Started {executable} but it never opened the bridge. Check the Blender "
                "window for an error, or press Start Bridge in the Aurum MCP panel.",
                is_error=True,
            )
        return text_result(f"Blender is up at {executable} and listening.")


def _render(name, result):
    if name == "blender_capture" and isinstance(result, dict):
        summary = {k: v for k, v in result.items() if k != "base64"}
        return f"{json.dumps(summary, indent=2)}\n\nSaved. Read the file to look at it."
    return json.dumps(result, indent=2, default=str)


# ── entry point ──────────────────────────────────────────────────────────────


def parse_arguments(argv):
    parser = argparse.ArgumentParser(
        prog="aurum_blender_mcp",
        description="Model Context Protocol server for Blender.",
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("AURUM_BLENDER_PORT", DEFAULT_PORT)))
    parser.add_argument("--token", default=os.environ.get("AURUM_BLENDER_TOKEN"))
    parser.add_argument(
        "--root",
        default=os.environ.get("AURUM_BLENDER_ROOT"),
        help="Where relative export and capture paths are written.",
    )
    parser.add_argument("--blender", default=os.environ.get("AURUM_BLENDER_EXE"),
                        help="Path to blender, for blender_launch.")
    parser.add_argument("--trace", action="store_true", help="Echo protocol traffic to stderr.")
    return parser.parse_args(argv)


def main(argv=None):
    options = parse_arguments(argv if argv is not None else sys.argv[1:])
    session = Session(options)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError as error:
            respond(None, error={"code": -32700, "message": f"parse error: {error}"})
            continue
        if options.trace:
            sys.stderr.write(f"--> {line}\n")
        try:
            session.handle(request)
        except Exception as error:  # noqa: BLE001 - a crash would end the session
            respond(
                request.get("id"),
                error={"code": -32603, "message": f"{type(error).__name__}: {error}"},
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
