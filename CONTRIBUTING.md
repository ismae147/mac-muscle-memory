# Contributing

Thanks for helping. Bug reports, compatibility reports ("works on my distro")
and pull requests are all welcome.

## Before you open a pull request

Install the tool you are changing, then run its checks. For accentpop:

```bash
./accentpop/install.sh     # once; the service runs your working copy

# data-level checks, no X needed
~/.local/share/accentpop/venv/bin/python accentpop/accentpop.py --selftest

# end-to-end against the running daemon (X11 session required)
systemctl --user restart accentpop
~/.local/share/accentpop/venv/bin/python accentpop/test_e2e.py
```

`test_e2e.py` opens its own focused GTK window and types into it, so injected
keys never reach your other windows. Do not use the keyboard while it runs.

Keep changes within the [design rules](README.md#design-rules): no root, no
system packages, reversible, and no logging of what people type.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(accentpop): add hold delay option
fix(accentpop): keep caret anchor after focus change
docs: clarify Wayland support
```

One logical change per commit. Keep docs and tests in the same commit as the
code they describe.

## Reporting bugs

Use the bug report form in the issue tracker. Input handling depends heavily on
the environment, so every report must include:

- **Distribution** and version (for example Ubuntu 24.04, Zorin OS 18)
- **Desktop environment** and version (for example GNOME 46)
- **Session type**: output of `echo $XDG_SESSION_TYPE`
- **Input method**: IBus, Fcitx or none (`ibus address` helps)
- **Application** where it happens, and how it was installed (deb, Flatpak, Snap, AppImage)
- The output of `journalctl --user -u accentpop -n 50 --no-pager`

The logs never contain what you typed, but read them before pasting anyway.
