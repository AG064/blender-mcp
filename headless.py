#!/usr/bin/env python3
"""Run Blender headless with the Aurum MCP bridge open.

    blender --background --python headless.py -- --root A:/project
    blender --background --python headless.py -- --port 9081 --token secret

This is the entry point for a modelling session with no window on it, which is
what an agent on a build machine needs. Blender passes everything after `--`
through to the script, so the options above are this file's own.

It is also the reason the add-on does not have to be installed for a headless
run: the add-on's directory is put on `sys.path` here, so a checkout works as
it stands. Installing is for the case where a person is driving Blender by
hand and wants the sidebar panel.
"""

import argparse
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON_PARENT = os.path.join(HERE, "addon")


def parse_arguments(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    parser = argparse.ArgumentParser(prog="headless.py")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AURUM_BLENDER_PORT", 9081)))
    parser.add_argument("--token", default=os.environ.get("AURUM_BLENDER_TOKEN"))
    parser.add_argument("--root", default=os.environ.get("AURUM_BLENDER_ROOT"))
    parser.add_argument("--blend", help="Open this file before listening.")
    return parser.parse_args(argv)


def main():
    options = parse_arguments(sys.argv)

    if ADDON_PARENT not in sys.path:
        sys.path.insert(0, ADDON_PARENT)

    import addon_utils

    addon_utils.enable("aurum_blender_mcp", default_set=False, persistent=True)
    from aurum_blender_mcp import get_bridge

    if options.blend:
        bpy.ops.wm.open_mainfile(filepath=options.blend)

    info = get_bridge().start(options.port, options.token, options.root)
    # Printed rather than logged: whoever started this is watching stdout for
    # exactly this line, to know when the bridge is ready to take commands.
    print(f"AURUM_BRIDGE_READY port={info['port']} blender={bpy.app.version_string}", flush=True)

    get_bridge().serve_forever()


if __name__ == "__main__":
    main()
