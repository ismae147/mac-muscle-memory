#!/usr/bin/env python3
"""accentpop - macOS-style press-and-hold accent character picker for X11.

Hold a letter key for ~300ms and a popup appears at the text caret with the
accented variants of that letter, each numbered. Press the number (or move with
Left/Right and confirm with Enter/Space) to replace the plain letter that was
already typed with the accented one. Escape cancels.

Design notes:
  * Two X connections. XRecord demands a dedicated connection of its own, so a
    second one is used for XTEST injection and keyboard-control calls.
  * XRecord runs in a daemon thread and never touches GTK directly; every
    hand-off to the GTK main loop goes through GLib.idle_add.
  * Per-key autorepeat is disabled for the trigger keys so that holding a key
    types exactly one character. It is restored on exit.
"""

import atexit
import contextlib
import os
import subprocess
import signal
import sys
import threading
import time

# --- variant map -----------------------------------------------------------
# Lowercase entries; the uppercase set is produced with .upper() per entry.
VARIANTS = {
    "a": ["à", "á", "â", "ä", "æ", "ã", "å", "ā"],
    "e": ["è", "é", "ê", "ë", "ē", "ė", "ę"],
    "i": ["î", "ï", "í", "ī", "į", "ì"],
    "o": ["ô", "ö", "ò", "ó", "œ", "ø", "ō", "õ"],
    "u": ["û", "ü", "ù", "ú", "ū"],
    "n": ["ñ", "ń"],
    "c": ["ç", "ć", "č"],
    "y": ["ÿ", "ý"],
    "s": ["ß", "ś", "š"],
    "z": ["ž", "ź", "ż"],
    "l": ["ł"],
    "g": ["ğ"],
    "d": ["ð"],
    "t": ["þ"],
    "r": ["ŕ"],
    "w": ["ŵ"],
    "k": ["ķ"],
    # Spanish inverted punctuation. '?' and '!' need Shift on a US layout, so
    # the trigger is the bare slash key.
    "/": ["¿", "¡"],
}

# "ß".upper() is the two-character "SS", which we can never inject as a single
# keysym, so the shifted set for 's' is spelled out instead.
UPPER_OVERRIDES = {"s": ["Ś", "Š"]}

# Triggers that are not letters keep their variants untransformed.
NO_UPPER = {"/"}

HOLD_MS = 300
SELECTED_BG = "#0A84FF"

# X keysym names used to resolve each trigger to a keycode at runtime.
KEYSYM_NAMES = {"/": "slash"}


def unicode_keysym(ch):
    """X keysym for an arbitrary Unicode character.

    Latin-1 characters must use their legacy keysym (equal to the code point);
    some toolkits ignore the 0x01000000-based form for that range.
    """
    code = ord(ch)
    if 0x20 <= code <= 0x7E or 0xA0 <= code <= 0xFF:
        return code
    return 0x01000000 + code


def variants_for(trigger, shift):
    """Variant list for a trigger key, honouring the Shift modifier."""
    if not shift or trigger in NO_UPPER:
        return list(VARIANTS[trigger])
    if trigger in UPPER_OVERRIDES:
        return list(UPPER_OVERRIDES[trigger])
    return [c.upper() for c in VARIANTS[trigger]]


# --- selftest --------------------------------------------------------------

def selftest():
    for trigger, chars in VARIANTS.items():
        assert chars, "empty variant list for %r" % trigger
        assert len(set(chars)) == len(chars), "duplicate variants for %r" % trigger
        for ch in chars:
            assert len(ch) == 1, "multi-char variant %r for %r" % (ch, trigger)
        upper = variants_for(trigger, shift=True)
        assert upper, "empty uppercase set for %r" % trigger
        assert len(set(upper)) == len(upper), "duplicate uppercase variants for %r" % trigger
        for ch in upper:
            assert len(ch) == 1, "uppercase transform of %r yields %r" % (trigger, ch)
    for ch in "aÀ¿ñ":
        assert unicode_keysym(ch) == ord(ch)
    for ch in "ŕœŁ":
        assert unicode_keysym(ch) == 0x01000000 + ord(ch)
    print("selftest OK")


# --- everything below needs X ----------------------------------------------

if "--selftest" not in sys.argv:
    from Xlib import X, XK, display
    from Xlib.ext import record, xtest
    from Xlib.protocol import rq

    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gio, GLib, Gtk

    try:
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError):
        Atspi = None   # popup falls back to the mouse pointer

# Populated in main().
inject_disp = None          # connection used for XTEST + keyboard control
record_disp = None          # dedicated XRecord connection
trigger_by_keycode = {}     # keycode -> trigger character
restore_autorepeat = None   # callable set up at startup

# GTK-thread-only state.
pending = {"source": None, "keycode": None, "trigger": None, "shift": False}
popup = None                # dict with the live popup, or None
ibus_conn = None            # kept alive for the IBus caret monitor


def log(*args):
    print("accentpop:", *args, flush=True)


def err(*args):
    print("accentpop:", *args, file=sys.stderr, flush=True)


# --- autorepeat ------------------------------------------------------------

def setup_autorepeat(disp, keycodes):
    """Disable autorepeat for the trigger keys; return a restore callable."""
    try:
        for kc in keycodes:
            disp.change_keyboard_control(auto_repeat_mode=0, key=kc)
        disp.sync()

        def restore():
            try:
                for kc in keycodes:
                    disp.change_keyboard_control(auto_repeat_mode=1, key=kc)
                disp.sync()
            except Exception as exc:  # connection may already be gone
                err("per-key autorepeat restore failed (%s), using xset r on" % exc)
                subprocess.run(["xset", "r", "on"], check=False)

        log("autorepeat disabled for %d trigger keys via XChangeKeyboardControl" % len(keycodes))
        return restore
    except Exception as exc:
        err("change_keyboard_control unusable (%s), falling back to xset" % exc)

    for kc in keycodes:
        subprocess.run(["xset", "-r", str(kc)], check=False)
    log("autorepeat disabled for %d trigger keys via xset" % len(keycodes))
    return lambda: subprocess.run(["xset", "r", "on"], check=False)


def cleanup():
    global restore_autorepeat
    restore, restore_autorepeat = restore_autorepeat, None
    close_popup(None)
    if restore is not None:
        restore()
        log("autorepeat restored")
    if slot_pool:
        restore_slots()
        log("injection keycodes restored")


# --- character injection ---------------------------------------------------

def tap(keycode):
    xtest.fake_input(inject_disp, X.KeyPress, keycode)
    xtest.fake_input(inject_disp, X.KeyRelease, keycode)
    inject_disp.sync()


# Characters are injected through spare keycodes that stay mapped for the
# whole session. Remapping a keycode right before tapping it and restoring it
# right after is a race: slow clients (Qt WebEngine, Flatpak apps such as
# ZapZap) translate the keycode after the restore and drop the character, so
# only the BackSpace lands. Common Spanish characters are mapped at startup so
# they never need a remap; anything else is loaded into a slot on demand and
# stays there until evicted or until exit.
PRELOAD = "ñáéíóú¿¡ÑÁÉÍÓÚü"
KEEP_FREE_KEYCODES = 4      # leave some for xdotool and similar tools
DYNAMIC_SLOTS = 2           # slots kept for characters outside PRELOAD
REMAP_SETTLE_SECONDS = 0.08  # let clients refetch the keymap after a remap
BACKSPACE_SETTLE_SECONDS = 0.08

slots = {}                  # char -> keycode, insertion order is LRU order
slot_pool = []              # keycodes reserved for slots
slot_originals = {}         # keycode -> original keysym row


def spare_keycodes(disp):
    """All keycodes whose keysyms are all zero, highest first, with rows."""
    lo = disp.display.info.min_keycode
    hi = disp.display.info.max_keycode
    mapping = disp.get_keyboard_mapping(lo, hi - lo + 1)
    return [(lo + offset, list(mapping[offset]))
            for offset in range(len(mapping) - 1, -1, -1)
            if not any(mapping[offset])]


def map_slot(keycode, ch):
    inject_disp.change_keyboard_mapping(keycode, [[unicode_keysym(ch)] * 4])
    inject_disp.sync()


def setup_slots():
    """Reserve spare keycodes and preload the common characters."""
    spare = spare_keycodes(inject_disp)
    for keycode, row in spare[:max(0, len(spare) - KEEP_FREE_KEYCODES)]:
        slot_pool.append(keycode)
        slot_originals[keycode] = row
    preload_count = max(0, len(slot_pool) - DYNAMIC_SLOTS)
    for ch, keycode in zip(PRELOAD[:preload_count], slot_pool):
        map_slot(keycode, ch)
        slots[ch] = keycode
    log("reserved %d keycodes for injection, %d characters preloaded"
        % (len(slot_pool), len(slots)))


def restore_slots():
    for keycode in slot_pool:
        try:
            inject_disp.change_keyboard_mapping(keycode, [slot_originals[keycode]])
        except Exception:
            pass
    slots.clear()
    slot_pool.clear()
    try:
        inject_disp.sync()
    except Exception:
        pass


def slot_for(ch):
    """Keycode that currently types ch, mapping it into a slot if needed."""
    keysym = unicode_keysym(ch)
    keycode = slots.pop(ch, None)
    if keycode is not None:
        slots[ch] = keycode  # mark as most recently used
        # Someone else (setxkbmap, a layout switch) may have reset it.
        if inject_disp.get_keyboard_mapping(keycode, 1)[0][0] == keysym:
            return keycode
    else:
        used = set(slots.values())
        free = [kc for kc in slot_pool if kc not in used]
        if free:
            keycode = free[0]
        else:
            # Evict the oldest on-demand character, never a preloaded one
            # unless nothing else is left.
            evicted = next((c for c in slots if c not in PRELOAD),
                           next(iter(slots)))
            keycode = slots.pop(evicted)
        slots[ch] = keycode
    map_slot(keycode, ch)
    time.sleep(REMAP_SETTLE_SECONDS)
    return keycode


def send_char(ch):
    """Inject an arbitrary character through a persistent keycode slot."""
    if not slot_pool:
        err("no spare keycode available, cannot insert character")
        return
    tap(slot_for(ch))


def _held_ignored_modifier_keys():
    """Keycodes of Ctrl/Alt/Super keys that are physically held right now."""
    state = inject_disp.screen().root.query_pointer().mask
    if not (state & IGNORED_MODS):
        return []
    modmap = inject_disp.get_modifier_mapping()
    keymap = inject_disp.query_keymap()
    held = []
    for index, mask in ((2, X.ControlMask), (3, X.Mod1Mask), (6, X.Mod4Mask)):
        if not (state & mask):
            continue
        for keycode in modmap[index]:
            if keycode and keymap[keycode >> 3] & (1 << (keycode & 7)):
                held.append(keycode)
    return held


@contextlib.contextmanager
def modifiers_cleared():
    """Release held Ctrl/Alt/Super for the duration of an injection.

    XTEST events are processed against the live modifier state, so injecting
    BackSpace while Ctrl is held would delete a whole word instead of one
    character. keyd maps left Alt onto a Ctrl-based layer here, which makes a
    stray Ctrl far more likely than on a stock keyboard.
    """
    try:
        held = _held_ignored_modifier_keys()
    except Exception as exc:
        err("could not read modifier state: %s" % exc)
        held = []
    for keycode in held:
        xtest.fake_input(inject_disp, X.KeyRelease, keycode)
    if held:
        inject_disp.sync()
    try:
        yield
    finally:
        for keycode in reversed(held):
            xtest.fake_input(inject_disp, X.KeyPress, keycode)
        if held:
            inject_disp.sync()


def tap_backspace():
    """Delete the character before the caret; False if BackSpace is unmapped."""
    backspace = inject_disp.keysym_to_keycode(XK.XK_BackSpace)
    if not backspace:
        err("BackSpace keycode not found")
        return False
    tap(backspace)
    return True


def insert_variant(ch):
    """Replace the already-typed plain letter with the chosen variant."""
    try:
        with modifiers_cleared():
            if tap_backspace():
                # With an input method (IBus) in between, keys are processed
                # asynchronously: the variant arrives as an IM commit that can
                # overtake the BackSpace, which then deletes the variant
                # instead of the plain letter. Let the BackSpace settle first.
                time.sleep(BACKSPACE_SETTLE_SECONDS)
            send_char(ch)
    except Exception as exc:
        err("injection failed: %s" % exc)
    return False


def wait_key_released(keycode, timeout=1.0):
    """Block until keycode is up; XTEST drops presses of a key already down."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        keymap = inject_disp.query_keymap()
        if not keymap[keycode >> 3] & (1 << (keycode & 7)):
            return
        time.sleep(0.01)


def delete_typed_letter():
    """BackSpace pressed in the popup: remove the plain letter, like macOS."""
    try:
        backspace = inject_disp.keysym_to_keycode(XK.XK_BackSpace)
        if backspace:
            wait_key_released(backspace)   # the user's own BackSpace
        with modifiers_cleared():
            tap_backspace()
    except Exception as exc:
        err("injection failed: %s" % exc)
    return False


# --- popup -----------------------------------------------------------------

CSS = """
window.accentpop { background-color: transparent; }
.accentpop-panel {
  background-color: %(panel)s;
  border: 1px solid %(border)s;
  border-radius: 12px;
  padding: 8px;
}
.accentpop-chip { border-radius: 8px; padding: 2px 8px 4px 8px; }
.accentpop-chip.selected { background-color: %(accent)s; }
.accentpop-char { font-size: 26px; color: %(fg)s; }
.accentpop-num { font-size: 10px; color: %(dim)s; }
.accentpop-chip.selected .accentpop-char,
.accentpop-chip.selected .accentpop-num { color: #ffffff; }
"""

LIGHT = {"panel": "rgba(250,250,252,0.97)", "border": "rgba(0,0,0,0.15)",
         "fg": "#1c1c1e", "dim": "rgba(28,28,30,0.55)", "accent": SELECTED_BG}
DARK = {"panel": "rgba(44,44,48,0.97)", "border": "rgba(255,255,255,0.14)",
        "fg": "#f2f2f7", "dim": "rgba(242,242,247,0.55)", "accent": SELECTED_BG}


def install_css():
    settings = Gtk.Settings.get_default()
    dark = False
    try:
        dark = bool(settings.get_property("gtk-application-prefer-dark-theme"))
    except Exception:
        pass
    provider = Gtk.CssProvider()
    provider.load_from_data((CSS % (DARK if dark else LIGHT)).encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def paint_selection():
    for i, chip in enumerate(popup["chips"]):
        ctx = chip.get_style_context()
        if i == popup["index"]:
            ctx.add_class("selected")
        else:
            ctx.remove_class("selected")


# --- caret tracking --------------------------------------------------------
# X11 does not expose where the text cursor is; only the focused application
# knows. Two sources are combined, newest wins:
#   * IBus: every client using the input method reports its caret rectangle
#     (in screen coordinates) so IBus can place its candidate window. This
#     covers Chromium/QtWebEngine apps such as ZapZap, which emit no AT-SPI
#     caret events at all. We only monitor SetCursorLocation calls.
#   * AT-SPI: caret events from toolkits that expose text accessibility.
#     Events are only trusted from the process owning the active window;
#     terminals keep emitting caret events (and claiming focus) while they
#     print output in the background.
# We read geometry only and never the text itself.

CARET_STALE_SECONDS = 15.0
ibus_caret = {"rect": None, "when": 0.0}
atspi_caret = {"text": None, "pid": None, "rect": None, "when": 0.0}
# Last left click: people usually click where they are about to type, so it
# beats the current mouse pointer for apps that report no caret at all.
last_click = {"pos": None, "when": 0.0}
CLICK_LINE_HEIGHT = 18


def caret_rect_of(text):
    """Screen rect of the character at the caret, or None."""
    offset = text.get_caret_offset()
    for probe in (offset, offset - 1):
        if probe < 0:
            continue
        rect = text.get_character_extents(probe, Atspi.CoordType.SCREEN)
        if rect and rect.height > 0 and (rect.x or rect.y):
            return (rect.x, rect.y, rect.width, rect.height)
    return None


def remember_caret(event):
    """AT-SPI callback: cache whichever text object last moved its caret."""
    try:
        text = event.source.get_text_iface()
        if text is None:
            return
        rect = caret_rect_of(text)
        if rect:
            atspi_caret.update(text=text, pid=event.source.get_process_id(),
                               rect=rect, when=time.time())
    except Exception:
        pass   # dead accessible, or an app with no usable text interface


def start_atspi_tracking():
    if Atspi is None:
        log("AT-SPI unavailable")
        return
    try:
        Atspi.init()
        for name in ("object:text-caret-moved", "focus:",
                     "object:state-changed:focused"):
            Atspi.EventListener.new(remember_caret).register(name)
        log("caret tracking active via AT-SPI")
    except Exception as exc:
        err("AT-SPI caret tracking unavailable (%s)" % exc)


def on_ibus_message(_conn, message, incoming):
    """GDBus filter (worker thread): record caret rects reported to IBus."""
    if not incoming:
        return message   # our own AddMatch calls
    if message.get_interface() == "org.freedesktop.IBus.Panel":
        member = message.get_member()
        if member == "SetCursorLocation":
            x, y, w, h = message.get_body().unpack()
            if h > 0 and (x or y):
                ibus_caret.update(rect=(x, y, w, h), when=time.time())
        elif member == "FocusOut":
            ibus_caret["rect"] = None
    if message.get_message_type() in (Gio.DBusMessageType.METHOD_RETURN,
                                      Gio.DBusMessageType.ERROR):
        return message   # replies to our own calls, e.g. BecomeMonitor
    return None   # never answer eavesdropped calls meant for the panel


def on_add_match(conn, result):
    try:
        conn.call_finish(result)
    except Exception as exc:
        err("IBus caret tracking unavailable (%s)" % exc)


def start_ibus_tracking():
    global ibus_conn
    try:
        address = subprocess.run(["ibus", "address"], capture_output=True,
                                 text=True, timeout=3).stdout.strip()
        if not address or "(null)" in address:
            raise RuntimeError("ibus-daemon is not running")
        ibus_conn = Gio.DBusConnection.new_for_address_sync(
            address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None)
        ibus_conn.add_filter(on_ibus_message)
        # ibus-daemon has no BecomeMonitor; eavesdropping match rules work.
        # Asynchronous on purpose: the filter runs on the GDBus worker thread
        # and needs the GIL, which a blocking call_sync would hold.
        for member in ("SetCursorLocation", "FocusOut"):
            ibus_conn.call(
                "org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus", "AddMatch",
                GLib.Variant("(s)", ("eavesdrop='true',type='method_call',"
                                     "interface='org.freedesktop.IBus.Panel',"
                                     "member='%s'" % member,)),
                None, Gio.DBusCallFlags.NONE, 3000, None, on_add_match)
        log("caret tracking active via IBus")
    except Exception as exc:
        err("IBus caret tracking unavailable (%s)" % exc)


def start_caret_tracking():
    start_ibus_tracking()
    start_atspi_tracking()


def active_window_pid():
    try:
        root = inject_disp.screen().root
        active = root.get_full_property(
            inject_disp.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
        win = inject_disp.create_resource_object("window", active.value[0])
        pid = win.get_full_property(
            inject_disp.intern_atom("_NET_WM_PID"), X.AnyPropertyType)
        return pid.value[0] if pid else None
    except Exception:
        return None


def atspi_rect_now():
    """Live caret rect from AT-SPI, only if it belongs to the active window."""
    if atspi_caret["rect"] is None or atspi_caret["pid"] != active_window_pid():
        return None
    text = atspi_caret["text"]
    try:
        return caret_rect_of(text) or atspi_caret["rect"]
    except Exception:
        atspi_caret.update(text=None, rect=None)   # died with its app
        return None


def caret_rect_now():
    """Best anchor rect for the popup, or None to fall back to the pointer.

    Fresh caret reports win, newest first, unless the last click is newer
    still. An old click is used only when no caret source answers.
    """
    now = time.time()
    carets = []
    if ibus_caret["rect"] is not None:
        carets.append((ibus_caret["when"], lambda: ibus_caret["rect"]))
    if atspi_caret["rect"] is not None:
        carets.append((atspi_caret["when"], atspi_rect_now))
    carets = sorted((c for c in carets if now - c[0] <= CARET_STALE_SECONDS),
                    key=lambda c: c[0], reverse=True)

    click_rect = None
    if last_click["pos"] is not None:
        x, y = last_click["pos"]
        click_rect = (x, y - CLICK_LINE_HEIGHT // 2, 1, CLICK_LINE_HEIGHT)
        if not carets or last_click["when"] > carets[0][0]:
            return click_rect

    for _when, get in carets:
        rect = get()
        if rect:
            return rect
    return click_rect


def place_window(win):
    """Anchor the popup at the text caret, falling back to the mouse pointer."""
    gdk_display = Gdk.Display.get_default()
    _minimum, natural = win.get_preferred_size()
    w, h = natural.width, natural.height

    rect = caret_rect_now()
    if rect is not None:
        cx, cy, cw, ch = rect
        anchor_x, anchor_y = cx, cy
        x = cx + cw // 2 - w // 2      # centred on the caret, like macOS
        y = cy + ch + 6                # just under the text line
        above = cy - h - 6
    else:
        _screen, px, py = gdk_display.get_default_seat().get_pointer().get_position()
        anchor_x, anchor_y = px, py
        x, y = px + 14, py + 18
        above = py - h - 6

    monitor = gdk_display.get_monitor_at_point(anchor_x, anchor_y)
    area = monitor.get_workarea() if monitor else None
    if area:
        if y + h > area.y + area.height and above >= area.y:
            y = above                  # no room below the line, flip above it
        x = max(area.x, min(x, area.x + area.width - w))
        y = max(area.y, min(y, area.y + area.height - h))
    win.move(x, y)


def show_popup(trigger, shift):
    global popup
    chars = variants_for(trigger, shift)[:9]

    win = Gtk.Window(type=Gtk.WindowType.POPUP)
    win.get_style_context().add_class("accentpop")
    win.set_keep_above(True)
    win.set_app_paintable(True)
    screen = win.get_screen()
    visual = screen.get_rgba_visual()
    if visual is not None and screen.is_composited():
        win.set_visual(visual)

    panel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    panel.get_style_context().add_class("accentpop-panel")
    win.add(panel)

    chips = []
    for i, ch in enumerate(chars):
        chip = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        chip.get_style_context().add_class("accentpop-chip")
        char_label = Gtk.Label(label=ch)
        char_label.get_style_context().add_class("accentpop-char")
        num_label = Gtk.Label(label=str(i + 1))
        num_label.get_style_context().add_class("accentpop-num")
        chip.pack_start(char_label, False, False, 0)
        chip.pack_start(num_label, False, False, 0)
        panel.pack_start(chip, False, False, 0)
        chips.append(chip)

    popup = {"win": win, "chips": chips, "chars": chars, "index": 0, "grabbed": False}
    paint_selection()

    win.connect("key-press-event", on_popup_key)
    win.connect("focus-out-event", on_popup_focus_out)

    place_window(win)
    win.show_all()

    seat = Gdk.Display.get_default().get_default_seat()
    status = seat.grab(win.get_window(), Gdk.SeatCapabilities.KEYBOARD,
                       True, None, None, None, None)
    if status == Gdk.GrabStatus.SUCCESS:
        popup["grabbed"] = True
    else:
        err("keyboard grab failed (%s); number keys may leak to the focused app" % status)
    return False


def close_popup(chosen):
    """Hide the popup, always release the grab, then inject once released."""
    global popup
    live, popup = popup, None
    if live is None:
        return
    try:
        if live["grabbed"]:
            Gdk.Display.get_default().get_default_seat().ungrab()
    except Exception as exc:
        err("ungrab failed: %s" % exc)
    finally:
        try:
            live["win"].destroy()
        except Exception:
            pass
        # Inject only after the grab is gone and the window is down.
        if chosen:
            GLib.idle_add(insert_variant, chosen)


def on_popup_focus_out(_win, _event):
    close_popup(None)
    return False


def on_popup_key(_win, event):
    if popup is None:
        return True
    key = event.keyval
    if key == Gdk.KEY_Escape:
        close_popup(None)
    elif Gdk.KEY_1 <= key <= Gdk.KEY_9:
        i = key - Gdk.KEY_1
        if i < len(popup["chars"]):
            close_popup(popup["chars"][i])
    elif key in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
        popup["index"] = max(0, popup["index"] - 1)
        paint_selection()
    elif key in (Gdk.KEY_Right, Gdk.KEY_KP_Right):
        popup["index"] = min(len(popup["chars"]) - 1, popup["index"] + 1)
        paint_selection()
    elif key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
        close_popup(popup["chars"][popup["index"]])
    elif key == Gdk.KEY_BackSpace:
        close_popup(None)   # releases the grab before we inject
        GLib.idle_add(delete_typed_letter)
    # Swallow everything else so it never reaches the focused application.
    return True


# --- hold detection (GTK thread) -------------------------------------------

IGNORED_MODS = 0  # Control / Alt / Super; filled in by main()


def cancel_pending():
    if pending["source"] is not None:
        GLib.source_remove(pending["source"])
    pending["source"] = None
    pending["keycode"] = None


def on_hold_elapsed():
    pending["source"] = None
    trigger, shift = pending["trigger"], pending["shift"]
    pending["keycode"] = None
    if popup is None:
        show_popup(trigger, shift)
    return False


def on_key_event(is_press, keycode, state):
    if popup is not None:
        return False
    if not is_press:
        if keycode == pending["keycode"]:
            cancel_pending()
        return False
    if state & IGNORED_MODS:
        cancel_pending()
        return False
    trigger = trigger_by_keycode.get(keycode)
    if trigger is None:
        cancel_pending()
        return False
    cancel_pending()
    pending["keycode"] = keycode
    pending["trigger"] = trigger
    pending["shift"] = bool(state & X.ShiftMask)
    pending["source"] = GLib.timeout_add(HOLD_MS, on_hold_elapsed)
    return False


# --- XRecord (its own thread, its own connection) --------------------------

def record_callback(reply):
    if reply.category != record.FromServer or reply.client_swapped:
        return
    if not reply.data or reply.data[0] < 2:
        return  # reply, not an event
    data = reply.data
    while len(data):
        event, data = rq.EventField(None).parse_binary_value(
            data, record_disp.display, None, None)
        if event.type in (X.KeyPress, X.KeyRelease):
            GLib.idle_add(on_key_event, event.type == X.KeyPress,
                          event.detail, event.state)
        elif event.type == X.ButtonPress and event.detail == 1:
            last_click.update(pos=(event.root_x, event.root_y), when=time.time())


def record_loop(ctx):
    try:
        record_disp.record_enable_context(ctx, record_callback)
        err("XRecord context ended unexpectedly")
    except Exception as exc:
        err("XRecord connection died: %s" % exc)
    finally:
        try:
            record_disp.record_free_context(ctx)
        except Exception:
            pass
        GLib.idle_add(fatal_exit)


def fatal_exit():
    cleanup()
    Gtk.main_quit()
    os._exit(1)


# --- startup ---------------------------------------------------------------

def resolve_triggers(disp):
    mapping = {}
    for trigger in VARIANTS:
        name = KEYSYM_NAMES.get(trigger, trigger)
        keysym = XK.string_to_keysym(name)
        keycode = disp.keysym_to_keycode(keysym) if keysym else 0
        if not keycode:
            err("trigger %r does not exist in the current layout, skipped" % trigger)
            continue
        mapping[keycode] = trigger
    return mapping


def on_signal():
    cleanup()
    Gtk.main_quit()
    return False


def main():
    global inject_disp, record_disp, trigger_by_keycode, restore_autorepeat, IGNORED_MODS

    # keyd turns Alt combos into Ctrl combos, so both must be filtered out.
    IGNORED_MODS = X.ControlMask | X.Mod1Mask | X.Mod4Mask

    if not os.environ.get("DISPLAY"):
        err("DISPLAY is not set. Run: systemctl --user import-environment DISPLAY XAUTHORITY")
        return 1

    try:
        inject_disp = display.Display()
        record_disp = display.Display()   # XRecord requires a dedicated connection
    except Exception as exc:
        err("cannot open X display: %s" % exc)
        return 1

    if not record_disp.has_extension("RECORD"):
        err("the X RECORD extension is missing; accentpop cannot observe keys")
        return 1

    try:
        # Stops autorepeat from emitting synthetic KeyRelease events that would
        # look like the user letting go of the key.
        record_disp.xkb_set_detectable_auto_repeat(True)
    except Exception as exc:
        err("detectable autorepeat unavailable in this python-xlib build (%s); "
            "harmless, autorepeat is already off for every trigger key" % exc)

    trigger_by_keycode = resolve_triggers(inject_disp)
    if not trigger_by_keycode:
        err("no trigger keys could be resolved, nothing to do")
        return 1

    if not Gtk.init_check(None)[0]:
        err("Gtk.init failed (no usable display?)")
        return 1
    install_css()

    restore_autorepeat = setup_autorepeat(inject_disp, sorted(trigger_by_keycode))
    atexit.register(cleanup)
    setup_slots()
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, on_signal)

    ctx = record_disp.record_create_context(
        0,
        [record.AllClients],
        [{
            "core_requests": (0, 0),
            "core_replies": (0, 0),
            "ext_requests": (0, 0, 0, 0),
            "ext_replies": (0, 0, 0, 0),
            "delivered_events": (0, 0),
            "device_events": (X.KeyPress, X.ButtonPress),
            "errors": (0, 0),
            "client_started": False,
            "client_died": False,
        }],
    )
    threading.Thread(target=record_loop, args=(ctx,), daemon=True).start()
    start_caret_tracking()

    log("watching %d trigger keys, hold %dms to open the picker" %
        (len(trigger_by_keycode), HOLD_MS))
    Gtk.main()
    cleanup()
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    sys.exit(main())
