# Product

<!-- impeccable:product-schema 1 -->

> Inferred without an interview from README.md, accentpop/README.md, docs/LAUNCH.md and CONTRIBUTING.md. Assumptions are marked.

## Platform

web

## Stack

static HTML/CSS/JS, single file at docs/index.html, served by GitHub Pages from /docs on main. No build step.

## Users

Linux desktop users (GNOME on X11) who came from macOS, or who write in Spanish, French, German or Portuguese on a US keyboard layout, and miss press-and-hold accents. Technically comfortable: they clone repos and run shell scripts. They arrive from Reddit (r/linux, r/gnome, r/Ubuntu) or GitHub.

## Product Purpose

mac-muscle-memory is a collection of small, independent tools that bring macOS typing habits to Linux. The first tool, accentpop, is a press-and-hold accent picker: hold a letter about 300 ms and a numbered popup at the text caret offers accented variants. Success for the landing page: a visitor understands the habit in seconds, trusts it is safe (no root, reads no text), and installs it or stars the repo.

## Positioning

The popup appears at the real text caret (IBus and AT-SPI caret tracking), works in GTK apps, terminals and Chromium/Electron/Qt WebEngine apps including Flatpak, and installs per user with no root and full reversibility. Compose keys and dead keys solve the characters; accentpop preserves the habit.

## Operating Context

Evaluated from a browser, usually on the Linux desktop it would run on. Installed from a terminal with three commands. Runs as a systemd --user service.

## Capabilities and Constraints

- X11 only; Wayland not supported (XRecord and XTEST have no Wayland equivalent).
- Tested on Zorin OS 18 / GNOME Shell 46; other GNOME/X11 systems likely work.
- Keys: 1-9 insert, arrows move, Enter/Space insert highlighted, Esc cancels, BackSpace closes and deletes the letter. Shift gives uppercase. `/` gives ¿ ¡.
- Max 9 variants per trigger. 18 trigger keys.
- Roadmap items are ideas, not commitments.

## Brand Commitments

Name: mac-muscle-memory (repo), accentpop (tool). Author credited only as GitHub user ismae147. MIT license. Voice: plain, precise, honest about limits. Assumption: no logo or brand colors exist.

## Evidence on Hand

docs/demo.gif and docs/demo.png (real screenshots of the popup). No testimonials, user counts, stars or press: do not fabricate any.

## Product Principles

- Keep the habit, not the platform: behave like macOS where it matters.
- Know as little as possible: key codes and caret geometry only, never text, no network.
- Leave no trace: no root, no system packages, everything reversible.
- Say the limits out loud (X11 only, what the daemon can see).

## Accessibility & Inclusion

The in-page demo must work with keyboard and touch, respect reduced motion, and announce state changes to assistive technology.
