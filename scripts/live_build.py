#!/usr/bin/env python3
"""Build the reference mech in a running Blender, one stage at a time.

    python scripts/live_build.py

Starts the MCP server as a subprocess, opens a real Model Context Protocol
session with it, and sends one `blender_execute` per stage with a pause between
them -- so a person watching the Blender window sees the machine assemble
rather than appear.

This is the same server any client runs. Nothing here is special-cased for the
demonstration, which is the point: it is also the first time the add-on has been
driven in GUI mode rather than headless, and the first time anything has watched
it happen.
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(ROOT, "server", "aurum_blender_mcp.py")
PARTS = os.path.join(ROOT, "parts")

PREAMBLE = f'''
import sys, math
PARTS = r"{PARTS}"
if PARTS not in sys.path:
    sys.path.insert(0, PARTS)
import bpy, mathutils
import mech_kit as kit
import reference_mech as rm
'''


def stage_parts():
    """The build, split into the stages a person can follow."""
    return [
        ("clearing the file and making the materials", PREAMBLE + '''
rm.kit.reset()
rm._mats = rm.palette()
rm._parts = []
result = {"materials": len(bpy.data.materials), "objects": len(bpy.data.objects)}
'''),
        ("blocking in the legs", PREAMBLE + '''
mats = rm._mats
rm._parts += rm.leg(mats, 1)
rm._parts += rm.leg(mats, -1)
result = {"parts": len(rm._parts)}
'''),
        ("building the torso and the chest faceting", PREAMBLE + '''
rm._parts += rm.torso(rm._mats)
result = {"parts": len(rm._parts)}
'''),
        ("setting the head between the shoulders", PREAMBLE + '''
rm._parts += rm.head(rm._mats)
result = {"parts": len(rm._parts)}
'''),
        ("adding the backpack and its mast", PREAMBLE + '''
rm._parts += rm.backpack(rm._mats)
result = {"parts": len(rm._parts)}
'''),
        ("hanging the arms and the hands", PREAMBLE + '''
rm._parts += rm.arm(rm._mats, 1)
rm._parts += rm.arm(rm._mats, -1)
result = {"parts": len(rm._parts)}
'''),
        ("bolting on the weapons", PREAMBLE + '''
import weapons as wp
weapon_mats = wp.palette()

def place(builder, at):
    offset = mathutils.Vector(at)
    for obj in builder(weapon_mats):
        obj.location = obj.location + offset
        rm._parts.append(obj)

place(wp.autocannon, rm.HAND_R)
place(wp.arc_blade, rm.HAND_L)
place(wp.missile_pod, rm.POD_AT)
result = {"parts": len(rm._parts)}
'''),
        ("joining by material and building the joint hierarchy", PREAMBLE + '''
built = rm.build()
result = built["stats"]
'''),
        ("framing it in the viewport", PREAMBLE + '''
import bpy
scene = bpy.context.scene
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
bg = scene.world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.045, 0.05, 0.06, 1.0)
    bg.inputs[1].default_value = 1.0

for area in bpy.context.screen.areas:
    if area.type != "VIEW_3D":
        continue
    area.spaces.active.shading.type = "MATERIAL"
    for region in area.regions:
        if region.type == "WINDOW":
            with bpy.context.temp_override(area=area, region=region):
                bpy.ops.view3d.view_all()
result = {"framed": True}
'''),
    ]


class Session:
    """A live MCP session, spoken over the server's stdin and stdout."""

    def __init__(self, port):
        self.process = subprocess.Popen(
            [sys.executable, SERVER, "--port", str(port), "--root", ROOT],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            encoding="utf-8", bufsize=1,
        )
        self.counter = 0
        self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "live-build", "version": "1.0"},
        })

    def request(self, method, params=None):
        self.counter += 1
        message = {"jsonrpc": "2.0", "id": self.counter, "method": method}
        if params is not None:
            message["params"] = params
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("the MCP server closed the connection")
        return json.loads(line)

    def execute(self, code):
        reply = self.request("tools/call", {
            "name": "blender_execute", "arguments": {"code": code},
        })
        content = reply.get("result", {}).get("content", [{}])[0].get("text", "")
        if reply.get("result", {}).get("isError"):
            raise RuntimeError(content)
        return content

    def close(self):
        try:
            self.process.stdin.close()
        except OSError:
            pass
        self.process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9081)
    parser.add_argument("--pause", type=float, default=1.6,
                        help="Seconds between stages, so a person can watch.")
    options = parser.parse_args()

    session = Session(options.port)
    try:
        for index, (label, code) in enumerate(stage_parts(), start=1):
            print(f"[{index}] {label}", flush=True)
            output = session.execute(code)
            for line in output.strip().splitlines():
                print(f"      {line}", flush=True)
            time.sleep(options.pause)
    finally:
        session.close()
    print("done", flush=True)


if __name__ == "__main__":
    main()
