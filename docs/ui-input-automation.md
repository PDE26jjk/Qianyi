# Driving the Blender UI with a synthetic mouse (verified recipe)

How to drive a running Blender from outside the process with a synthetic mouse
- clicks, drags and brush strokes - and verify every step through Blender's own
data. Used for interactive add-on testing, where the input has to travel the
real UI path but the assertion must not depend on screenshots.

For the project-specific bootstrap (workspace, Qianyi project tree, select tool,
N panel category) see `docs/ui-test-bootstrap.md`. Read its section 2b before
driving a UI that reads model temp data: the identities have to be refreshed
from a script context first, or the first panel draw raises "Writing to ID
classes in this context is not allowed".

To pick up edits to the add-on without losing the MCP connection, reload the
package in place: `docs/reload-without-restarting.md`.

## 1. Talk to the running Blender

The `MCP for Blender` add-on hosts a JSON socket server inside Blender:

- endpoint: `127.0.0.1:9876`
- request: one JSON object `{"type": "<command>", "params": {...}}`
- reply: `{"status": "success" | "error", "result": ...}`

Handshake with `get_addon_info` (`protocol_version`, `blender_version`,
`capabilities`). Commands used here: `ping`, `get_addon_info`, `execute_code`,
`get_scene_info`, `get_object_info`, `get_viewport_screenshot`.

`execute_code` runs Python on Blender's main thread and returns captured
stdout, so every read-back (coordinates, selection, mesh data, colours) goes
through it.

```python
import json, socket


class Blender:
    def __init__(self, host="127.0.0.1", port=9876, timeout=30):
        self.sock = socket.create_connection((host, port), timeout=timeout)

    def call(self, cmd, **params):
        self.sock.sendall(json.dumps({"type": cmd, "params": params}).encode())
        buf = b""
        while True:
            chunk = self.sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf.decode())
            except json.JSONDecodeError:
                continue
        return json.loads(buf.decode())

    def code(self, src):
        reply = self.call("execute_code", code=src)
        if reply.get("status") != "success":
            raise RuntimeError(reply)
        return reply["result"]["result"].strip()
```

## 2. Coordinate spaces

Blender's window, area and region coordinates are physical pixels with the
origin at the bottom-left of the client area.

- Declare the driver process DPI aware (`SetProcessDpiAwareness(2)`) so
  `GetClientRect` / `ClientToScreen` report the same physical space Blender
  uses.
- Region-space position of a 3D point, using the `WINDOW` region of the
  `VIEW_3D` area (region coordinates are window-relative, so add the region
  origin to get window coordinates):

```python
q = view3d_utils.location_3d_to_region_2d(region, region_3d, Vector(p))
```

- Window coordinates to screen pixels:

```python
screen_x = client_origin[0] + region.x + q.x
screen_y = client_origin[1] + (client_size[1] - (region.y + q.y))
```

- Verify before clicking: ray-cast the same pixel
  (`region_2d_to_origin_3d` + `region_2d_to_vector_3d` + `scene.ray_cast`) and
  compare the hit object with the expectation.

## 3. Injecting the mouse

Move the real cursor, then deliver window messages carrying **client-area**
coordinates packed into `lParam`:

```python
import time
import win32api, win32gui

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON = 0x0200, 0x0201, 0x0202, 1


def post(hwnd, origin, msg, wparam, screen_pt):
    x, y = screen_pt[0] - origin[0], screen_pt[1] - origin[1]
    win32gui.PostMessage(hwnd, msg, wparam, ((y & 0xFFFF) << 16) | (x & 0xFFFF))


def stroke(hwnd, origin, screen_points, gap=0.03, hold=0.12):
    win32api.SetCursorPos(screen_points[0])
    post(hwnd, origin, WM_MOUSEMOVE, 0, screen_points[0])
    time.sleep(0.08)
    post(hwnd, origin, WM_LBUTTONDOWN, MK_LBUTTON, screen_points[0])
    time.sleep(hold)
    for pt in screen_points[1:]:
        win32api.SetCursorPos(pt)
        post(hwnd, origin, WM_MOUSEMOVE, MK_LBUTTON, pt)
        time.sleep(gap)
    post(hwnd, origin, WM_LBUTTONUP, 0, screen_points[-1])
```

Two details that matter:

- Set the cursor with `SetCursorPos` before each posted move - Blender resolves
  events through the real cursor position.
- The window does not need to be in the foreground; the messages are delivered
  to the window directly.

Stroke pacing:

- annotation and drawing tools register at ~30 ms between points with a ~120 ms
  hold after the button-down;
- paint brushes accumulate through a stroke timer and need slower pacing
  (~60 ms between points, ~300 ms hold after the button-down).

Re-measure a widget's position from a **fresh screenshot before every click**.
Panel and header layouts shift between sessions and even during one session (the
node editor sidebar's first category tab moved from a 77 px to a 98 px offset
from the area top), and a click at a stale coordinate fails silently: nothing
raises, the widget is simply not hit. Verify every click with a data read-back
instead of assuming it landed.

Repeated clicks on the same widget are fine. Measured the same checkbox twice in
three paces - 50 ms apart, ~1 s apart, and with the pointer moved away and back
in between - and both clicks registered every time, so no special handling is
needed for repeats.

The target window does not have to be focused: window messages are delivered
directly, so Blender may stay in the background while it is driven. It does have
to be *visible* - a minimized window reports zero-size regions and no usable
coordinates.

## 3b. Editors other than the 3D viewport

The same client-to-screen mapping applies, but 2D editors get their region pixel
from the region's own view data instead of a 3D projection:

```python
region = next(r for r in area.regions if r.type == 'WINDOW')
q = region.view2d.view_to_region(node.location.x, node.location.y)   # node editor
```

Verified in a Node Editor (Compositor tree): a click computed this way selected
the node, and a drag of 120 x 70 screen pixels moved its `location` by exactly
`120 / zoom` and `70 / zoom` in node space, with the Blender window in the
background.

## 6b. Screenshots of any editor

`get_viewport_screenshot` (the MCP command) renders the 3D viewport offscreen
and needs a `VIEW_3D` area. For every other editor - and for the whole window -
use Blender's own screenshot operators with a context override:

```python
bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)      # force a repaint first
with bpy.context.temp_override(window=w, area=area, region=region):
    bpy.ops.screen.screenshot_area(filepath=r"...\editor.png")   # one editor
    bpy.ops.screen.screenshot(filepath=r"...\window.png")        # whole window
```

Both were verified with the Blender window in the background: the editor
screenshot showed the node tree with its selection highlight, and the window
screenshot showed the node editor, outliner, properties and timeline together.
Call the redraw first whenever the capture must reflect a change made in the
same session.

## 7. Workspaces and area layout (verified)

```python
# create a workspace from the current layout and switch to it
bpy.ops.workspace.duplicate()
w = bpy.context.window
w.workspace.name = 'Layout_3D_Node'

# split the largest area vertically, then give each half its own editor type
main = max(w.screen.areas, key=lambda a: a.width * a.height)
region = next(r for r in main.regions if r.type == 'WINDOW')
before = {a.as_pointer() for a in w.screen.areas}
with bpy.context.temp_override(window=w, area=main, region=region):
    bpy.ops.screen.area_split(direction='VERTICAL', factor=0.5)
new_area = next(a for a in w.screen.areas if a.as_pointer() not in before)
new_area.type = 'VIEW_3D'        # left half
main.type = 'NODE_EDITOR'        # right half
```

Usage notes:

- `Area` has no `name`; identify areas through `as_pointer()`. A split replaces
  the original `Area` object, so capture the pointers before and diff after.
- A freshly split area reports a zero-size rect until the next redraw; re-read
  the layout (or force a redraw) before computing pixel coordinates from it.
- `workspace.duplicate()` puts the copy on screen, but `bpy.context.workspace`
  may still report the previous workspace; read `bpy.context.window.workspace`
  back before renaming anything.
- Workspaces and layout live in the `.blend`; they persist only if the file is
  saved.

Available area operators: `screen.area_split`, `area_join`, `area_swap`,
`area_move`, `area_dupli`, `area_close`, `screen_full_area`;
workspace operators: `workspace.duplicate`, `add`, `delete`,
`reorder_to_front`, `reorder_to_back`.

Verified: a vertical split with `VIEW_3D` on the left and `NODE_EDITOR` on the
right in a new workspace, captured with `screen.screenshot`.

## 4. Drawing a stroke (verified)

Activate a drawing tool through the API with a context override - the MCP
context has no area, so the plain operator call is rejected:

```python
w = bpy.context.window
a = next(x for x in w.screen.areas if x.type == 'VIEW_3D')
r = next(x for x in a.regions if x.type == 'WINDOW')
with bpy.context.temp_override(window=w, area=a, region=r, space_data=a.spaces.active):
    bpy.ops.wm.tool_set_by_id(name='builtin.annotate')
```

Project the path sample by sample, inject it, and read the stroke back:

```python
gp = bpy.data.grease_pencils['Annotations']
strokes = gp.layers[0].frames[0].strokes          # strokes[i].points
```

Measured: a 40-sample projected arc produced one stroke of 87 sampled points;
running the same path again produced an identical second stroke.

## 5. Painting colour (verified)

Vertex colours on a mesh:

```python
bpy.ops.object.mode_set(mode='VERTEX_PAINT')
ups = bpy.context.tool_settings.unified_paint_settings
ups.use_unified_color = False                     # otherwise the unified colour wins
bpy.context.tool_settings.vertex_paint.brush.color = (1.0, 0.0, 0.0)
```

Inject the stroke with paint pacing, then read the attribute:

```python
ob = bpy.data.objects['PaintProbe']
ca = ob.data.color_attributes.active_color         # corner domain, byte colour
colours = [tuple(round(c, 3) for c in ca.data[i].color) for i in range(len(ca.data))]
```

Measured: the synthetic stroke set the affected corner elements exactly to
`(1.0, 0.0, 0.0, 1.0)`.

## 6. Screenshots for visual confirmation

`get_viewport_screenshot(filepath=..., max_size=1200)` renders the 3D viewport
offscreen into a PNG; it works with the Blender window in the background.
Keep the data read-back as the assertion and use the screenshot to confirm that
what was drawn looks like what was intended.
