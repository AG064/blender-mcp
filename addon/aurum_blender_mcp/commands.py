"""The command table: everything the bridge can be asked to do.

Split from the socket handling so that every operation can also be called
directly from Blender's own Python console while developing, and so that the
transport has no idea what a mesh is.

Every handler takes the bridge's `context` and a dict of arguments, and returns
a JSON-serialisable value or raises `CommandError`. Raising is the only way to
report a failure: a handler that returns `{"error": ...}` would be indistinguish-
able from a tool whose result happens to have an `error` key.

Nothing here uses a third-party module. Blender ships a complete Python, but the
set of packages it ships changes between releases, and an add-on that needs
`numpy` works until somebody runs it in a build without it.
"""

import base64
import json
import math
import os
import sys
import traceback

import bpy
import mathutils


class CommandError(Exception):
    """A command that was understood and refused."""


# ── helpers ──────────────────────────────────────────────────────────────────


def _object(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise CommandError(f"no object named {name!r}")
    return obj


def _vec(values, default=None):
    if values is None:
        if default is None:
            raise CommandError("a vector is required")
        return mathutils.Vector(default)
    if isinstance(values, (int, float)):
        return mathutils.Vector((values, values, values))
    if len(values) != 3:
        raise CommandError(f"a vector needs three numbers, got {len(values)}")
    return mathutils.Vector((float(values[0]), float(values[1]), float(values[2])))


def _selected(context):
    """The objects a command applies to.

    An explicit list of names wins; otherwise whatever is selected in the UI.
    The fallback is what makes the add-on usable by hand as well as by an agent:
    a person selects a thing and asks for a bevel, and the agent names the
    things it means.
    """
    names = context.arguments.get("objects")
    if names:
        return [_object(name) for name in names]
    chosen = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not chosen:
        raise CommandError(
            "nothing selected and no objects named; pass 'objects' or select in the UI"
        )
    return chosen


def _mode(mode):
    """Switch interaction mode, ignoring a request to enter the mode we are in."""
    if bpy.context.mode != mode:
        bpy.ops.object.mode_set(mode=mode)


def _ensure_object_mode():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _deselect_all():
    for obj in bpy.context.selected_objects:
        obj.select_set(False)


def _activate(obj):
    _deselect_all()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _add_object(obj):
    """Put a newly created datablock into the scene collection."""
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _mesh_stats(obj):
    if obj.type != "MESH":
        return {}
    mesh = obj.data
    return {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
    }


def _describe(obj):
    return {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "dimensions": list(obj.dimensions),
        "parent": obj.parent.name if obj.parent else None,
        "visible": obj.visible_get(),
        "mesh": _mesh_stats(obj),
    }


def _screenshot_path(context, name):
    """Where a capture should be written.

    Inside the project when the bridge was given one, so that frames land beside
    the work rather than in a temporary directory nobody looks in.
    """
    root = context.root or bpy.app.tempdir
    directory = os.path.join(root, "blender-captures")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, name)


# ── the commands ─────────────────────────────────────────────────────────────


def cmd_status(context, arguments):
    return {
        "running": True,
        "blender_version": bpy.app.version_string,
        "python_version": sys.version.split()[0],
        "background": bpy.app.background,
        "file": bpy.data.filepath or None,
        "dirty": bpy.data.is_dirty,
        "root": context.root,
        "port": context.port,
        "objects": len(bpy.data.objects),
        "scene": bpy.context.scene.name,
    }


def cmd_execute(context, arguments):
    """Run Python inside Blender.

    The escape hatch, and the reason the tool list can stay small: anything the
    named commands do not cover is one expression away, and the agent writing
    that expression has the whole of `bpy` in front of it. The result is
    whatever the code binds to `result`, which keeps the contract explicit
    rather than guessing at the last expression's value.
    """
    code = arguments.get("code")
    if not code:
        raise CommandError("'code' is required")

    scope = {"bpy": bpy, "mathutils": mathutils, "math": math, "result": None}
    stdout = []

    class _Tee:
        def write(self, text):
            stdout.append(text)

        def flush(self):
            pass

    real_stdout = sys.stdout
    sys.stdout = _Tee()
    try:
        # A single expression is the common case, and evaluating it as a value
        # means `2 + 2` answers 4 instead of needing `result = 2 + 2`.
        try:
            value = eval(compile(code, "<blender-mcp>", "eval"), scope)
            scope["result"] = value
        except SyntaxError:
            exec(compile(code, "<blender-mcp>", "exec"), scope)
    except Exception:
        raise CommandError(traceback.format_exc(limit=6))
    finally:
        sys.stdout = real_stdout

    return {
        "result": _jsonable(scope.get("result")),
        "stdout": "".join(stdout)[-8000:],
    }


def _jsonable(value, depth=0):
    """Coerce a Blender value into something JSON can carry.

    Deliberately shallow and conservative: a `bpy` result can be a graph of
    objects that reaches most of the file, and serialising that would produce a
    response larger than the request by orders of magnitude.
    """
    if depth > 4:
        return repr(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, depth + 1) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (mathutils.Vector, mathutils.Euler, mathutils.Color)):
        return list(value)
    if isinstance(value, mathutils.Quaternion):
        return list(value)
    if isinstance(value, mathutils.Matrix):
        return [list(row) for row in value]
    if hasattr(value, "name"):
        return value.name
    return repr(value)


def cmd_scene_info(context, arguments):
    scene = bpy.context.scene
    return {
        "name": scene.name,
        "frame": scene.frame_current,
        "frame_range": [scene.frame_start, scene.frame_end],
        "unit_scale": scene.unit_settings.scale_length,
        "collections": [c.name for c in bpy.data.collections],
        "objects": [_describe(o) for o in scene.objects],
        "materials": [m.name for m in bpy.data.materials],
        "cameras": [o.name for o in scene.objects if o.type == "CAMERA"],
        "lights": [o.name for o in scene.objects if o.type == "LIGHT"],
    }


def cmd_object_list(context, arguments):
    kind = arguments.get("type")
    objects = [o for o in bpy.data.objects if kind is None or o.type == kind]
    return {"count": len(objects), "objects": [_describe(o) for o in objects]}


def cmd_object_create(context, arguments):
    kind = arguments.get("type", "CUBE").upper()
    name = arguments.get("name")
    location = arguments.get("location", [0, 0, 0])
    rotation = arguments.get("rotation", [0, 0, 0])
    scale = arguments.get("scale", [1, 1, 1])
    size = arguments.get("size", 1.0)

    factory = {
        "CUBE": lambda: bpy.ops.mesh.primitive_cube_add(size=size),
        "SPHERE": lambda: bpy.ops.mesh.primitive_uv_sphere_add(radius=size / 2),
        "CYLINDER": lambda: bpy.ops.mesh.primitive_cylinder_add(radius=size / 2, depth=size),
        "CONE": lambda: bpy.ops.mesh.primitive_cone_add(radius1=size / 2, depth=size),
        "TORUS": lambda: bpy.ops.mesh.primitive_torus_add(major_radius=size / 2, minor_radius=size / 8),
        "PLANE": lambda: bpy.ops.mesh.primitive_plane_add(size=size),
        "EMPTY": lambda: bpy.ops.object.empty_add(),
        "CAMERA": lambda: bpy.ops.object.camera_add(),
        "LIGHT": lambda: bpy.ops.object.light_add(),
    }
    if kind not in factory:
        raise CommandError(f"unknown type {kind!r}; try one of {sorted(factory)}")

    _ensure_object_mode()
    factory[kind]()
    obj = bpy.context.active_object
    obj.location = _vec(location)
    obj.rotation_euler = _vec(rotation)
    obj.scale = _vec(scale, [1, 1, 1])
    if name:
        obj.name = name
        if obj.data is not None:
            obj.data.name = name
    return _describe(obj)


def cmd_object_set(context, arguments):
    obj = _object(arguments["object"])
    for key in ("location", "rotation", "scale"):
        if key in arguments:
            default = [0, 0, 0] if key != "scale" else [1, 1, 1]
            setattr(obj, f"{key}_euler" if key == "rotation" else key, _vec(arguments[key], default))
    if "visible" in arguments:
        obj.hide_viewport = not arguments["visible"]
        obj.hide_render = not arguments["visible"]
    if "parent" in arguments:
        parent = arguments["parent"]
        obj.parent = _object(parent) if parent else None
    if "name" in arguments:
        obj.name = arguments["name"]
    return _describe(obj)


def cmd_object_delete(context, arguments):
    names = arguments.get("objects")
    if not names:
        names = [o.name for o in _selected(context)]
    removed = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        bpy.data.objects.remove(obj, do_unlink=True)
        removed.append(name)
    return {"removed": removed}


def cmd_object_duplicate(context, arguments):
    names = arguments.get("objects") or [o.name for o in _selected(context)]
    offset = _vec(arguments.get("offset"), [0, 0, 0])
    made = []
    for name in names:
        source = _object(name)
        copy = source.copy()
        if source.data is not None:
            copy.data = source.data.copy()
        _add_object(copy)
        copy.location = source.location + offset
        made.append(copy.name)
    return {"created": made}


def cmd_object_join(context, arguments):
    names = arguments.get("objects") or [o.name for o in _selected(context)]
    if len(names) < 2:
        raise CommandError("joining needs at least two objects")
    _ensure_object_mode()
    target = _object(names[0])
    _activate(target)
    for name in names[1:]:
        _object(name).select_set(True)
    bpy.ops.object.join()
    return _describe(bpy.context.active_object)


def cmd_object_apply_transform(context, arguments):
    _ensure_object_mode()
    applied = []
    for obj in _selected(context):
        _activate(obj)
        bpy.ops.object.transform_apply(
            location=arguments.get("location", False),
            rotation=arguments.get("rotation", True),
            scale=arguments.get("scale", True),
        )
        applied.append(obj.name)
    return {"applied": applied}


def cmd_mesh_from_data(context, arguments):
    """Build a mesh from explicit vertices and faces.

    The reason this exists rather than only primitives: a mech is a lot of
    bevelled boxes at exact sizes, and describing them as numbers is both
    faster and more reviewable than driving the UI's box tool repeatedly.
    """
    name = arguments.get("name", "mesh")
    vertices = arguments.get("vertices")
    faces = arguments.get("faces")
    if not vertices or not faces:
        raise CommandError("'vertices' and 'faces' are required")

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in vertices], [], [tuple(f) for f in faces])
    mesh.validate(verbose=False)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _add_object(obj)
    if "location" in arguments:
        obj.location = _vec(arguments["location"])
    if "rotation" in arguments:
        obj.rotation_euler = _vec(arguments["rotation"])
    return _describe(obj)


def cmd_mesh_bevel(context, arguments):
    width = float(arguments.get("width", 0.02))
    segments = int(arguments.get("segments", 2))
    applied = []
    for obj in _selected(context):
        _activate(obj)
        modifier = obj.modifiers.new(name="bevel", type="BEVEL")
        modifier.width = width
        modifier.segments = segments
        modifier.limit_method = arguments.get("limit", "ANGLE")
        modifier.angle_limit = math.radians(float(arguments.get("angle", 30)))
        if arguments.get("apply", True):
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        applied.append(obj.name)
    return {"beveled": applied, "width": width, "segments": segments}


def cmd_mesh_boolean(context, arguments):
    """Union, difference or intersect the selected objects into the first."""
    operation = arguments.get("operation", "UNION").upper()
    if operation not in ("UNION", "DIFFERENCE", "INTERSECT"):
        raise CommandError("operation must be UNION, DIFFERENCE or INTERSECT")
    names = arguments.get("objects") or [o.name for o in _selected(context)]
    if len(names) < 2:
        raise CommandError("a boolean needs a target and at least one cutter")

    _ensure_object_mode()
    target = _object(names[0])
    for name in names[1:]:
        cutter = _object(name)
        _activate(target)
        modifier = target.modifiers.new(name=f"bool_{cutter.name}", type="BOOLEAN")
        modifier.operation = operation
        modifier.object = cutter
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
    return _describe(target)


def cmd_mesh_modifier(context, arguments):
    """Add a modifier, optionally applying it.

    Left unapplied by default for the generators — a mirror or an array that is
    still live is editable, and the exported glTF has it evaluated either way.
    """
    kind = arguments.get("modifier", "MIRROR").upper()
    apply_now = bool(arguments.get("apply", False))
    results = []
    for obj in _selected(context):
        _activate(obj)
        modifier = obj.modifiers.new(name=kind.lower(), type=kind)
        for key, value in (arguments.get("settings") or {}).items():
            setattr(modifier, key, value)
        if apply_now:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        results.append({"object": obj.name, "modifier": modifier.name})
    return {"added": results}


def cmd_material_new(context, arguments):
    name = arguments.get("name", "material")
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    settings = arguments.get("settings") or {}
    _apply_principled(material, settings)
    return {"name": material.name, "settings": _read_principled(material)}


def cmd_material_set(context, arguments):
    material = bpy.data.materials.get(arguments["material"])
    if material is None:
        raise CommandError(f"no material named {arguments['material']!r}")
    material.use_nodes = True
    _apply_principled(material, arguments.get("settings") or {})
    return {"name": material.name, "settings": _read_principled(material)}


def _apply_principled(material, settings):
    """Set the handful of Principled inputs that matter for a hard-surface kit.

    Named rather than passed through by socket name, because the input list is
    reordered between Blender releases and an index-based setter silently
    changes colour into roughness on the next version.
    """
    for node in material.node_tree.nodes:
        if node.type != "BSDF_PRINCIPLED":
            continue
        for key, value in settings.items():
            socket = node.inputs.get(key) or node.inputs.get(key.replace("_", " ").title())
            if socket is None:
                continue
            if key == "Base Color" and len(value) == 3:
                value = [*value, 1.0]
            socket.default_value = value
    return material


def _read_principled(material):
    for node in material.node_tree.nodes:
        if node.type != "BSDF_PRINCIPLED":
            continue
        out = {}
        for name in ("Base Color", "Metallic", "Roughness", "Emission Color", "Emission Strength", "Alpha"):
            socket = node.inputs.get(name)
            if socket is None:
                continue
            value = socket.default_value
            try:
                out[name] = list(value)
            except TypeError:
                out[name] = value
        return out
    return {}


def cmd_material_assign(context, arguments):
    material = bpy.data.materials.get(arguments["material"])
    if material is None:
        raise CommandError(f"no material named {arguments['material']!r}")
    slot = int(arguments.get("slot", 0))
    assigned = []
    for obj in _selected(context):
        if obj.type != "MESH":
            continue
        if obj.data.materials:
            if slot < len(obj.data.materials):
                obj.data.materials[slot] = material
            else:
                obj.data.materials.append(material)
        else:
            obj.data.materials.append(material)
        assigned.append(obj.name)
    return {"assigned": assigned, "material": material.name}


def cmd_material_list(context, arguments):
    return {
        "materials": [
            {"name": m.name, "settings": _read_principled(m) if m.use_nodes else {}}
            for m in bpy.data.materials
        ]
    }


def cmd_export_gltf(context, arguments):
    """Write the scene, or a named selection, as glTF."""
    path = arguments.get("path")
    if not path:
        raise CommandError("'path' is required")
    if context.root and not os.path.isabs(path):
        path = os.path.join(context.root, path)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

    fmt = arguments.get("format", "GLB").upper()
    if fmt not in ("GLB", "GLTF_SEPARATE", "GLTF_EMBEDDED"):
        raise CommandError("format must be GLB, GLTF_SEPARATE or GLTF_EMBEDDED")

    only = arguments.get("objects")
    if only:
        _ensure_object_mode()
        _deselect_all()
        for name in only:
            _object(name).select_set(True)
        bpy.context.view_layer.objects.active = _object(only[0])

    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format=fmt,
        use_selection=bool(only),
        export_apply=bool(arguments.get("apply_modifiers", True)),
        export_yup=bool(arguments.get("y_up", True)),
        export_materials="EXPORT",
    )
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return {"path": path, "bytes": size, "format": fmt}


def cmd_import_gltf(context, arguments):
    path = arguments.get("path")
    if not path:
        raise CommandError("'path' is required")
    if context.root and not os.path.isabs(path):
        path = os.path.join(context.root, path)
    if not os.path.exists(path):
        raise CommandError(f"no file at {path}")

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    added = [o.name for o in bpy.data.objects if o not in before]
    return {"path": path, "imported": added}


def cmd_capture(context, arguments):
    """Save a picture of what Blender is looking at.

    Rendered rather than grabbed from the screen, because the interesting case
    is an agent working with Blender in the background where there is no screen
    to grab. It means the scene needs a camera; when it has none, one is placed
    to frame everything, which is what a person would do before taking the
    picture anyway.
    """
    name = arguments.get("name", "capture.png")
    width = int(arguments.get("width", 960))
    height = int(arguments.get("height", 600))
    path = _screenshot_path(context, name)

    scene = bpy.context.scene
    created_camera = False
    if scene.camera is None:
        _frame_scene_with_a_new_camera()
        created_camera = True

    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    scene.render.film_transparent = bool(arguments.get("transparent", False))

    engine = arguments.get("engine")
    if engine:
        scene.render.engine = engine
    elif scene.render.engine == "BLENDER_WORKBENCH" or bpy.app.background:
        # Workbench is instant and needs no lights, which is what a capture
        # during modelling wants. A lit render is available by asking for it.
        try:
            scene.render.engine = "BLENDER_WORKBENCH"
        except TypeError:
            pass

    bpy.ops.render.render(write_still=True)
    if created_camera:
        scene.camera = None

    if not os.path.exists(path):
        raise CommandError("Blender rendered but wrote nothing")

    payload = None
    if arguments.get("inline", False):
        with open(path, "rb") as handle:
            payload = base64.b64encode(handle.read()).decode("ascii")

    return {"path": path, "bytes": os.path.getsize(path), "base64": payload}


def _frame_scene_with_a_new_camera():
    """Place a camera that sees everything, the way 'frame all' would."""
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise CommandError("there is nothing to photograph")

    corners = []
    for obj in meshes:
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ mathutils.Vector(corner))
    low = mathutils.Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    high = mathutils.Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    centre = (low + high) / 2
    radius = max((high - low).length / 2, 0.5)

    direction = mathutils.Vector((1.0, -1.4, 0.75)).normalized()
    camera_data = bpy.data.cameras.new("mcp_capture_camera")
    camera = bpy.data.objects.new("mcp_capture_camera", camera_data)
    _add_object(camera)
    camera.location = centre + direction * radius * 3.0
    look = (centre - camera.location).normalized()
    camera.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera
    return camera


def cmd_save(context, arguments):
    path = arguments.get("path")
    if path:
        if context.root and not os.path.isabs(path):
            path = os.path.join(context.root, path)
        bpy.ops.wm.save_as_mainfile(filepath=path)
    else:
        if not bpy.data.filepath:
            raise CommandError("this file has never been saved; pass 'path'")
        bpy.ops.wm.save_mainfile()
    return {"path": bpy.data.filepath}


def cmd_open(context, arguments):
    path = arguments.get("path")
    if not path:
        raise CommandError("'path' is required")
    if context.root and not os.path.isabs(path):
        path = os.path.join(context.root, path)
    if not os.path.exists(path):
        raise CommandError(f"no file at {path}")
    if bpy.data.is_dirty and not arguments.get("discard_changes", False):
        raise CommandError(
            "the open file has unsaved changes; save them or pass discard_changes"
        )
    bpy.ops.wm.open_mainfile(filepath=path)
    result = {"path": bpy.data.filepath}
    if bpy.app.background:
        # Loading a file rebuilds Blender's Python environment, which ends the
        # script this bridge is running inside. Saying so beats the agent
        # discovering it on the next call.
        result["warning"] = (
            "a background Blender rebuilds its Python environment when a file is "
            "opened, so this bridge has almost certainly gone with it; reconnect "
            "and start it again"
        )
    return result


def cmd_new_scene(context, arguments):
    """Empty the file. Refuses while there is unsaved work unless told to.

    Done by deleting datablocks rather than by `read_factory_settings`. That
    operator does not merely clear the file: it tears down and rebuilds the
    Python environment, which in a background Blender ends the script that is
    running and with it the bridge. An agent asked for an empty scene and got a
    disconnected Blender, which is a spectacular way to answer a small request.
    """
    if bpy.data.is_dirty and not arguments.get("discard_changes", False):
        raise CommandError(
            "the open file has unsaved changes; save them or pass discard_changes"
        )

    _ensure_object_mode()
    collections = [
        name
        for name in arguments.get("keep_collections", [])
        if name in bpy.data.collections
    ]

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        if collection.name not in collections:
            bpy.data.collections.remove(collection)

    # Orphaned meshes, materials and images are not just clutter: an export
    # walks the data, and a scene "emptied" but still holding the previous
    # model's materials is a scene that leaks them into the next one.
    for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                       bpy.data.lights, bpy.data.curves, bpy.data.images):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)

    if arguments.get("units", True):
        bpy.context.scene.unit_settings.system = "METRIC"
        bpy.context.scene.unit_settings.scale_length = 1.0

    if arguments.get("save_path"):
        path = arguments["save_path"]
        if context.root and not os.path.isabs(path):
            path = os.path.join(context.root, path)
        bpy.ops.wm.save_as_mainfile(filepath=path)

    return {
        "scene": bpy.context.scene.name,
        "objects": len(bpy.data.objects),
        "materials": len(bpy.data.materials),
        "file": bpy.data.filepath or None,
    }


COMMANDS = {
    "status": cmd_status,
    "execute": cmd_execute,
    "scene_info": cmd_scene_info,
    "object_list": cmd_object_list,
    "object_create": cmd_object_create,
    "object_set": cmd_object_set,
    "object_delete": cmd_object_delete,
    "object_duplicate": cmd_object_duplicate,
    "object_join": cmd_object_join,
    "object_apply_transform": cmd_object_apply_transform,
    "mesh_from_data": cmd_mesh_from_data,
    "mesh_bevel": cmd_mesh_bevel,
    "mesh_boolean": cmd_mesh_boolean,
    "mesh_modifier": cmd_mesh_modifier,
    "material_new": cmd_material_new,
    "material_set": cmd_material_set,
    "material_assign": cmd_material_assign,
    "material_list": cmd_material_list,
    "export_gltf": cmd_export_gltf,
    "import_gltf": cmd_import_gltf,
    "capture": cmd_capture,
    "save": cmd_save,
    "open": cmd_open,
    "new_scene": cmd_new_scene,
}
