# Aurum Blender MCP

Let an AI agent drive Blender. Any MCP client can use it — Codex, Claude Code,
Cursor, or an agent framework of your own.

An agent that can only write code cannot make a model. This is the missing half:
the agent builds geometry, assigns materials, takes a picture of what it made,
and exports glTF for the game engine — all through the Model Context Protocol.

## Install

```powershell
pwsh -File install.ps1
```

That copies the add-on into Blender, enables it, and registers the server with
whichever agents are on the machine. It installs nothing else: no packages, no
runtime, no build step. Both halves are standard-library Python.

Point it at a project so relative exports land beside the work:

```powershell
pwsh -File install.ps1 -Project A:\path\to\game
```

## Use

**With Blender open.** Enable *Aurum Blender MCP* in Preferences → Add-ons if
the installer did not, then press **Start Bridge** in the 3D viewport's
*Aurum MCP* sidebar. The add-on starts with Blender by default, so usually
there is nothing to press.

**Headless.** For a machine with no window on it:

```powershell
blender --background --python headless.py -- --root A:/project
```

It prints `AURUM_BRIDGE_READY port=9081` when it is listening. The add-on does
not have to be installed for this: `headless.py` puts the checkout on
`sys.path`, so a clone works as it stands.

## Registering it with an agent

The server speaks MCP over stdio, which is the transport every client supports.

```json
{
  "mcpServers": {
    "aurum-blender": {
      "command": "python",
      "args": ["A:/path/to/blender-mcp/server/aurum_blender_mcp.py",
               "--root", "A:/path/to/project"]
    }
  }
}
```

Where that file goes depends on the client:

| Client | File |
|---|---|
| Codex | `~/.codex/config.toml`, under `[mcp_servers.aurum-blender]` |
| Claude Code | `.mcp.json` in the project |
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` |
| Cursor | `~/.cursor/mcp.json` |
| Anything else | the standard config for that client |

`install.ps1` writes the ones it finds. `skills/blender-mcp/SKILL.md` is a
ready-made skill for agents that take instructions as markdown rather than as a
tool list.

### Options

| | |
|---|---|
| `--port` | Loopback port. Default 9081. |
| `--token` | Shared secret. Empty by default, because the socket is loopback-only. |
| `--root` | Where relative export and capture paths are written. |
| `--blender` | Path to Blender, for `blender_launch`. |
| `--trace` | Echo protocol traffic to stderr. |

## Tools

25 of them, listed by `tools/list`. The shape is deliberate: a small set of
precise operations plus one escape hatch.

| | |
|---|---|
| `blender_status` | Reachable? Which version? Unsaved work? |
| `blender_execute` | Run Python in Blender and return `result`. |
| `blender_scene_info`, `blender_object_list` | What is in the file. |
| `blender_object_create`, `_set`, `_delete`, `_duplicate`, `_join`, `_apply_transform` | Transform and organise. |
| `blender_mesh_from_data` | Build a mesh from explicit vertices and faces. |
| `blender_mesh_bevel` | The single change that most makes a box read as a part. |
| `blender_mesh_boolean` | Cut panels and recesses. |
| `blender_mesh_modifier` | Mirror, array, subsurf, solidify. |
| `blender_material_new`, `_set`, `_assign`, `_list` | Surfaces. |
| `blender_export_gltf`, `blender_import_gltf` | Interchange. |
| `blender_capture` | Render the scene to a PNG. |
| `blender_save`, `blender_open`, `blender_new_scene` | Files. |
| `blender_launch` | Start Blender if it is not up. |

`blender_execute` is why the list can stay this size. Anything not covered is
one expression away, and the agent writing it has the whole of `bpy` available.

## How it is put together

```
addon/aurum_blender_mcp/
  __init__.py   the add-on: preferences, panel, start and stop
  bridge.py     the socket, the queue, and the main-thread pump
  commands.py   every operation, in one table
server/
  aurum_blender_mcp.py   the MCP server
headless.py             Blender without a window
```

**Why a socket.** The MCP server is a separate process, started and stopped by
whatever client is driving the agent, and it has to talk to a Blender that is
already open with somebody's work in it. A socket is the only thing that fits
that shape: the add-on listens once, and clients come and go.

**Why the work happens on the main thread.** `bpy` is not thread-safe and a
socket accept loop is a thread. Commands go through a bounded queue that the
main thread drains — from a timer in the GUI, or from an explicit pump loop
under `--background` where there is no event loop to hang a timer on. The queue
rejects rather than grows, because a client that sends faster than Blender can
draw will never read its answers anyway.

**Why no dependencies.** An MCP server is the first thing somebody runs when
they try a tool out. It should not be able to fail because a package index was
unreachable or a virtual environment went stale. Blender ships a complete
Python, but which packages it ships changes between releases, so the add-on
uses the standard library only as well.

## Security

The bridge binds to `127.0.0.1` and cannot be configured otherwise, because a
socket that runs arbitrary Python in somebody's open Blender must not be
reachable from the network. `--token` adds a shared secret for a machine with
several users on it.

`blender_execute` runs whatever it is given, by design. Treat an agent with
this server attached as an agent with a shell in your Blender session, and give
it the same thought you would give any other tool that can run code.

## Limits

- **`blender_open` in background mode.** Loading a file rebuilds Blender's
  Python environment, which ends the script the bridge is running inside. The
  tool says so in its result rather than leaving you to find out on the next
  call. Use `--blend <file>` when starting headless instead.
- **`blender_new_scene` empties the file in place** rather than calling
  `read_factory_settings`, for the same reason: the operator tears down the
  Python environment, so an agent asking for an empty scene would be handed a
  disconnected Blender.
- **One Blender at a time per port.** A second Blender cannot start a bridge on
  a port the first is holding; the panel reports it rather than failing quietly.
