# Launch kit

Ready-to-paste text for publishing and announcing the repository.

Repository URL: `https://github.com/ismae147/mac-muscle-memory`

## GitHub repository description

Paste into *About → Description* (under 350 characters):

> macOS typing ergonomics for Linux. accentpop: hold a letter to pick an accented variant (ñ, é, ü, ¿) from a numbered popup at the text caret, like on a Mac. GNOME/X11, no root, per-user systemd service, reversible, no network.

## Topics

```
linux, gnome, x11, accents, spanish, macos, keyboard, ibus, python, gtk,
press-and-hold, input-method, accessibility, xorg, typing
```

## Social preview

Use [`demo.png`](demo.png) as the social preview image
(*Settings → General → Social preview*). GitHub recommends 1280×640; the
screenshot works as is, or place it on a 1280×640 canvas.

## Reddit

Post as a link or image post with the GIF ([`demo.gif`](demo.gif)), then add the
text as the first comment. Check each subreddit's self-promotion rules first.

### r/linux

**Title:** accentpop: macOS-style press-and-hold accents for GNOME on X11 (hold `n`, get `ñ`)

> I switched from macOS and kept reaching for press-and-hold to type accents.
> Compose keys and dead keys work, but the habit was hard to unlearn, so I
> wrote a small daemon for it.
>
> Hold a letter for ~300 ms and a numbered popup appears at the text caret.
> Press `1`–`9` to insert a variant, `Esc` to cancel. Shift gives uppercase,
> and holding `/` gives `¿ ¡`.
>
> - Finds the caret through IBus (Chromium, Electron, Qt WebEngine, Flatpak
>   apps) and AT-SPI (GTK), with click/pointer fallbacks.
> - No root, per-user venv, `systemd --user` service, restores everything on
>   exit.
> - Reads key codes and caret geometry only, never text. No network. One
>   Python file you can audit.
>
> X11 only for now. Tested on Zorin OS 18 / GNOME 46. Reports from other
> distros are very welcome.
>
> https://github.com/ismae147/mac-muscle-memory

### r/gnome

**Title:** Press-and-hold accent picker for GNOME (X11), macOS-style

> accentpop brings the macOS press-and-hold accent popup to GNOME on X11.
> Hold a letter, pick the variant by number, keep typing. The popup is a small
> GTK 3 window that follows the light/dark preference and anchors at the text
> caret via IBus or AT-SPI.
>
> It runs as a `systemd --user` service, needs no root and no system
> packages, and is fully reversible. Wayland is not supported yet, because it
> relies on XRecord and XTEST.
>
> Feedback on other GNOME versions is appreciated:
> https://github.com/ismae147/mac-muscle-memory

### r/Ubuntu

**Title:** Type ñ, é, ü without changing your keyboard layout: press-and-hold accents for Ubuntu (Xorg session)

> If you write in Spanish, French, German or Portuguese on a US keyboard,
> accentpop lets you hold a letter and pick the accented version from a
> popup, like on macOS.
>
> Install without sudo:
>
> ```
> git clone https://github.com/ismae147/mac-muscle-memory.git
> cd mac-muscle-memory
> ./accentpop/install.sh
> ```
>
> It needs the "Ubuntu on Xorg" session (gear icon on the login screen).
> Uninstalling is three commands, listed in the README.
>
> https://github.com/ismae147/mac-muscle-memory

### r/linuxmasterrace

**Title:** Left macOS, kept one habit: hold a key to get accents. Now it works on my Linux box

> Small weekend-sized project that turned into a proper tool: hold `e`, get
> `è é ê ë`. Works in browsers, Electron apps and Flatpaks, not just GTK.
> No root, no telemetry, one Python file.
>
> X11 only (sorry, Wayland friends, for now).
>
> https://github.com/ismae147/mac-muscle-memory

## X / Twitter

Attach [`demo.gif`](demo.gif).

> Missed macOS press-and-hold accents on Linux, so I built it.
>
> Hold a letter → numbered popup at the caret → press 1–9. ñ é ü ¿ without
> switching layouts.
>
> GNOME/X11, no root, reversible, no network, MIT.
>
> https://github.com/ismae147/mac-muscle-memory
>
> #Linux #GNOME #OpenSource

Short variant (under 280 characters with the link):

> Hold a key, get the accent. macOS-style press-and-hold accent picker for GNOME/X11: ñ é ü ¿ from a popup at the caret. No root, MIT. https://github.com/ismae147/mac-muscle-memory #Linux #GNOME

## Spanish version (for Spanish-speaking communities)

**Title:** accentpop: acentos al estilo macOS en Linux (mantén `n` y obtienes `ñ`)

> Si vienes de macOS, seguramente extrañas mantener presionada una tecla para
> escribir acentos. Hice una pequeña herramienta que lleva ese comportamiento a
> GNOME en X11.
>
> Mantén presionada una letra unos 300 ms y aparece, junto al cursor de texto,
> una ventana con sus variantes numeradas. Presiona `1`–`9` para insertarla o
> `Esc` para cancelar. Con `Shift` obtienes mayúsculas, y al mantener `/`
> aparecen `¿` y `¡`.
>
> - Funciona en navegadores, apps Electron, Qt WebEngine y Flatpak (vía IBus)
>   y en apps GTK (vía AT-SPI).
> - No requiere root: usa un entorno virtual por usuario y un servicio
>   `systemd --user`. Al detenerse, restaura todo lo que modificó.
> - Solo lee códigos de tecla y la posición del cursor, nunca el texto. Sin
>   conexión a internet.
>
> Por ahora solo funciona en X11. Probado en Zorin OS 18 con GNOME 46. Se
> agradecen reportes de otras distribuciones.
>
> https://github.com/ismae147/mac-muscle-memory
