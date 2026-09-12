"""Build every model ASHFRAME needs and write them out as glTF.

Run from Blender, headless or not:

    blender --background --python parts/build.py -- --out A:/path/to/models

Or from an agent, through the Blender MCP, which is how these were authored:

    blender_execute: exec(open(r".../parts/build.py").read().replace(...))

Each builder is a function that returns a report, so a failure names the model
that failed rather than the batch.
"""

import argparse
import importlib
import os
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# (module, builder function, output file). One GLB per mech so the game loads
# only what a given mission needs, and one for the props because they are always
# all there.
MODELS = [
    ("mechs", "player", "ashframe.glb"),
    ("mechs", "skirmisher", "skirmisher.glb"),
    ("mechs", "artillery", "artillery.glb"),
    ("mechs", "patriarch", "patriarch.glb"),
    ("props", "build", "arena_props.glb"),
]


def parse_arguments(argv):
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    parser = argparse.ArgumentParser(prog="build.py")
    parser.add_argument("--out", default=os.path.join(HERE, "..", "models"))
    parser.add_argument("--only", help="Build one model, by output name without the extension.")
    return parser.parse_args(argv)


def export(path, name):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=False,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )
    return {"file": os.path.basename(path), "bytes": os.path.getsize(path)}


def main():
    options = parse_arguments(sys.argv)
    out = os.path.abspath(options.out)
    reports = []

    for module_name, builder_name, filename in MODELS:
        label = filename.replace(".glb", "")
        if options.only and options.only != label:
            continue
        try:
            module = importlib.import_module(module_name)
            importlib.reload(module)
            built = getattr(module, builder_name)()
            written = export(os.path.join(out, filename), filename)
            report = {"model": label, **written, **built}
            # A model that arrives at two hundred thousand triangles is a bug
            # report rather than an asset, so say so here rather than in the
            # game where it costs a frame budget to find out.
            polygons = built.get("stats", {}).get("polygons", 0)
            report["budget"] = "ok" if polygons < 60000 else "OVER"
            reports.append(report)
        except Exception:
            reports.append({"model": label, "error": traceback.format_exc(limit=4)})

    for report in reports:
        print("AURUM_MODEL", report)
    print("AURUM_BUILD_DONE", len(reports))


if __name__ == "__main__":
    main()
