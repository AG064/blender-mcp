"""Aurum Blender MCP — let an agent drive Blender.

Blender is where the models for a game get made, and an agent that can only
write code cannot make one. This add-on opens a loopback socket and answers
commands that build meshes, assign materials, take pictures of what it is
looking at, and export glTF.

It is the Blender half of a pair. The other half is `server/aurum_blender_mcp.py`,
a Model Context Protocol server that any MCP client can run — Codex, Claude
Code, Cursor, or an agent framework of your own. Nothing about the pair is
specific to one of them.

Nothing here imports anything outside the standard library. Blender ships a
complete Python, but the packages it ships change between releases, and an
add-on that needs one works until somebody runs it in a build without it.
"""

bl_info = {
    "name": "Aurum Blender MCP",
    "author": "Aurum",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Aurum MCP",
    "description": "Drive Blender from an AI agent over the Model Context Protocol",
    "category": "Development",
}

import os

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel

from . import bridge

DEFAULT_PORT = 9081
_bridge = None


def get_bridge():
    global _bridge
    if _bridge is None:
        _bridge = bridge.Bridge()
    return _bridge


class AurumMCPPreferences(AddonPreferences):
    bl_idname = __name__

    port: IntProperty(
        name="Port",
        description="Loopback port the bridge listens on",
        default=DEFAULT_PORT,
        min=1024,
        max=65535,
    )
    token: StringProperty(
        name="Token",
        description="Optional shared secret; leave empty to accept any loopback client",
        default="",
        subtype="PASSWORD",
    )
    root: StringProperty(
        name="Working directory",
        description="Where exports and captures are written when a relative path is given",
        default="",
        subtype="DIR_PATH",
    )
    autostart: BoolProperty(
        name="Start with Blender",
        description="Open the bridge when Blender starts, so an agent can attach at any time",
        default=True,
    )


class AURUM_MCP_OT_start(Operator):
    bl_idname = "aurum_mcp.start"
    bl_label = "Start Bridge"
    bl_description = "Listen for an agent on the loopback port"

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        instance = get_bridge()
        if instance.running:
            self.report({"INFO"}, f"Already listening on port {instance.port}")
            return {"FINISHED"}
        try:
            info = instance.start(prefs.port, prefs.token or None, prefs.root or None)
        except OSError as error:
            # The usual cause is a second Blender or a stale process holding the
            # port. Saying so is more useful than the errno.
            self.report({"ERROR"}, f"Could not listen on port {prefs.port}: {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Listening on 127.0.0.1:{info['port']}")
        return {"FINISHED"}


class AURUM_MCP_OT_stop(Operator):
    bl_idname = "aurum_mcp.stop"
    bl_label = "Stop Bridge"
    bl_description = "Stop listening"

    def execute(self, context):
        get_bridge().stop()
        self.report({"INFO"}, "Bridge stopped")
        return {"FINISHED"}


class AURUM_MCP_PT_panel(Panel):
    bl_label = "Aurum MCP"
    bl_idname = "AURUM_MCP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Aurum MCP"

    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons[__name__].preferences
        instance = get_bridge()

        state = layout.box()
        if instance.running:
            state.label(text=f"Listening on 127.0.0.1:{instance.port}", icon="LINKED")
            state.label(text=f"{instance.requests_served} requests served")
            state.operator("aurum_mcp.stop", icon="PAUSE")
        else:
            state.label(text="Not listening", icon="UNLINKED")
            state.operator("aurum_mcp.start", icon="PLAY")

        settings = layout.box()
        settings.label(text="Settings")
        settings.prop(prefs, "port")
        settings.prop(prefs, "token")
        settings.prop(prefs, "root")
        settings.prop(prefs, "autostart")

        if instance.last_error:
            error = layout.box()
            error.label(text="Last error", icon="ERROR")
            for line in str(instance.last_error).splitlines()[-4:]:
                error.label(text=line[:90])


CLASSES = (
    AurumMCPPreferences,
    AURUM_MCP_OT_start,
    AURUM_MCP_OT_stop,
    AURUM_MCP_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    if not hasattr(bpy.types.Scene, "aurum_mcp_note"):
        bpy.types.Scene.aurum_mcp_note = StringProperty(default="")


def unregister():
    get_bridge().stop()
    if hasattr(bpy.types.Scene, "aurum_mcp_note"):
        del bpy.types.Scene.aurum_mcp_note
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


def _autostart():
    """Open the bridge on load, if the preference says so.

    Deferred to a timer because preferences are not readable during
    registration, and because a bridge opened halfway through start-up would be
    answering commands against a half-built context.
    """
    prefs = bpy.context.preferences.addons.get(__name__)
    if prefs is None or not prefs.preferences.autostart:
        return None
    instance = get_bridge()
    if instance.running:
        return None
    try:
        instance.start(prefs.preferences.port, prefs.preferences.token or None,
                       prefs.preferences.root or None)
    except OSError:
        # Another instance already has the port. Not worth a dialog: the panel
        # shows the state, and the usual reason is a second Blender.
        pass
    return None


@bpy.app.handlers.persistent
def _on_load(_dummy):
    bpy.app.timers.register(_autostart, first_interval=0.5)


def _install_handlers():
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)
    bpy.app.timers.register(_autostart, first_interval=1.0)
