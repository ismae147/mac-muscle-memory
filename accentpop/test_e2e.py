#!/usr/bin/env python3
"""End-to-end checks for accentpop against the running daemon.

Every check drives its own focused GTK window, so injected keys land there and
never in whatever you happen to have open.

    ~/.local/share/accentpop/venv/bin/python test_e2e.py

The daemon needs ~2s after a restart before it observes keys; this script waits
for that instead of racing it.
"""

import math
import sys
import time

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib          # noqa: E402
from Xlib import X, XK, display              # noqa: E402
from Xlib.ext import xtest                   # noqa: E402

READY_DELAY = 3.0       # seconds to let a freshly started daemon settle
HOLD_MS = 700           # longer than the daemon's 300ms trigger

disp = display.Display()
root = disp.screen().root


def keycode(name):
    return disp.keysym_to_keycode(XK.string_to_keysym(name))


KC = {n: keycode(n) for n in ("a", "2", "Control_L")}
KC_ESC = 9


def release_all():
    for kc in (KC["2"], KC["Control_L"], KC["a"]):
        try:
            xtest.fake_input(disp, X.KeyRelease, kc)
        except Exception:
            pass
    disp.sync()


def focus_at_end(entry):
    """Focus the entry with the caret at the end, nothing selected.

    Gtk.Entry.grab_focus() selects the whole buffer, which would make the first
    injected key replace the text instead of appending to it.
    """
    entry.grab_focus()
    entry.select_region(0, 0)
    entry.set_position(-1)


def popup_geometry():
    """Screen rect of the accentpop window, or None if it is not mapped."""
    for win in root.query_tree().children:
        try:
            attrs = win.get_attributes()
            if not (attrs.override_redirect and attrs.map_state == X.IsViewable):
                continue
            geom = win.get_geometry()
            origin = win.translate_coords(root, 0, 0)
            if 40 < geom.width < 900 and 20 < geom.height < 200:
                return (-origin.x, -origin.y, geom.width, geom.height)
        except Exception:
            continue
    return None


def run_case(hold_ctrl=False, move_window_to=None, warp_pointer_to=None):
    """Hold 'a', pick variant 2, return (entry text, popup rect, window origin)."""
    out = {}
    window = Gtk.Window()
    window.set_keep_above(True)
    window.set_default_size(340, 60)
    entry = Gtk.Entry()
    entry.set_text("prueba")
    window.add(entry)
    window.show_all()
    window.present()
    if move_window_to:
        window.move(*move_window_to)
    focus_at_end(entry)

    def start():
        if warp_pointer_to:
            root.warp_pointer(*warp_pointer_to)
            disp.sync()
        focus_at_end(entry)
        xtest.fake_input(disp, X.KeyPress, KC["a"])
        disp.sync()
        GLib.timeout_add(HOLD_MS, pick)
        return False

    def pick():
        out["popup"] = popup_geometry()
        out["origin"] = window.get_window().get_origin()[1:]
        if hold_ctrl:
            xtest.fake_input(disp, X.KeyPress, KC["Control_L"])
            disp.sync()
        xtest.fake_input(disp, X.KeyPress, KC["2"])
        xtest.fake_input(disp, X.KeyRelease, KC["2"])
        disp.sync()
        GLib.timeout_add(600, finish)
        return False

    def finish():
        release_all()
        out["text"] = entry.get_text()
        Gtk.main_quit()
        return False

    GLib.timeout_add(700, start)
    GLib.timeout_add(9000, lambda: (release_all(), Gtk.main_quit(), False)[-1])
    Gtk.main()
    release_all()
    window.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration()
    return out


def check(name, ok, detail):
    print("  %-46s %s  %s" % (name, "OK  " if ok else "FAIL", detail))
    return ok


def main():
    print("waiting %.0fs for the daemon to settle..." % READY_DELAY)
    time.sleep(READY_DELAY)
    results = []

    got = run_case()
    results.append(check("inserts the chosen variant",
                         got.get("text") == "pruebaá", repr(got.get("text"))))
    results.append(check("popup opens on hold",
                         got.get("popup") is not None, str(got.get("popup"))))

    # keyd maps left Alt onto a Ctrl layer, so a stray Ctrl is realistic here.
    # Without modifier clearing this injects Ctrl+BackSpace and eats a word.
    got = run_case(hold_ctrl=True)
    results.append(check("survives a physically held Ctrl",
                         got.get("text") == "pruebaá", repr(got.get("text"))))

    # Pointer is parked far away, so a pass proves the caret drove the position.
    got = run_case(move_window_to=(260, 240), warp_pointer_to=(1900, 1040))
    popup, origin = got.get("popup"), got.get("origin")
    if popup and origin:
        dist = lambda a, b: math.hypot(a[0] - b[0], a[1] - b[1])  # noqa: E731
        near_caret = dist(popup[:2], origin)
        near_mouse = dist(popup[:2], (1900, 1040))
        results.append(check("popup follows the caret, not the mouse",
                             near_caret < near_mouse,
                             "caret %dpx / mouse %dpx" % (near_caret, near_mouse)))
    else:
        results.append(check("popup follows the caret, not the mouse",
                             False, "popup not found"))

    print()
    if all(results):
        print("all %d checks passed" % len(results))
        return 0
    print("%d of %d checks failed" % (results.count(False), len(results)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
