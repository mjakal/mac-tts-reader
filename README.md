# mac-tts-reader

Read selected text aloud on macOS with Microsoft Edge neural voices. A local Python server stays running between requests, synthesizes speech through Edge TTS, and plays it from memory. The Bash client connects over `/tmp/enge_tts.sock` and starts the server when needed.

## Requirements

- macOS with Command Line Tools (`xcode-select --install`)
- Python 3 and Homebrew `jq` (`brew install python jq`)
- An internet connection for speech synthesis and the voice list

Install the Python dependencies in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt nuitka
```

## Run from source

Start `python server.py` in one terminal. In another, run `bash client.sh -t "Hello from macOS"`. The client looks for a built `tts-server` when it needs to start the server itself.

## Build and install

Build a standalone server distribution with Nuitka. The bundled NLTK data is used by `cleantext`:

```bash
NLTK_DATA="$(python -c 'import nltk; print(nltk.data.path[0])')"
python -m nuitka --mode=standalone --follow-imports \
  --include-module=_cffi_backend \
  --include-package-data=certifi \
  --include-data-dir="$NLTK_DATA"=nltk_data \
  --output-filename=tts-server \
  --output-folder-name=tts-server.dist server.py

mkdir -p ~/tts
cp -R tts-server.dist ~/tts/
install -m 755 client.sh ~/tts/tts-client
```

After rebuilding, replace the installed `~/tts/tts-server.dist` and restart the running server. The client starts `~/tts/tts-server.dist/tts-server` automatically when no server is available. Nuitka's `--onefile` mode can fail macOS code-signature checks, so use the standalone build shown here.

If speech fails with `Speech service returned HTTP 403`, upgrade the Python dependencies from `requirements.txt`, rebuild the standalone server, install the new distribution, and restart the running server. The bundled server keeps the `edge-tts` version present at build time; updating Python packages alone does not change an existing bundle.

## Use the client

```bash
~/tts/tts-client                          # Read clipboard text
~/tts/tts-client -t "Hello"               # Read supplied text
~/tts/tts-client -c                       # Same as no argument (--clipboard also works)
~/tts/tts-client -v hr-HR-GabrijelaNeural # Change voice
~/tts/tts-client --no-clean               # Skip text cleaning
~/tts/tts-client -g                       # Toggle: stop, or read clipboard text
~/tts/tts-client -g -v hr-HR-GabrijelaNeural # Toggle with a Croatian voice
~/tts/tts-client -s                       # Stop playback
~/tts/tts-client -l                       # List available voices
```

With no text argument, the client reads the current clipboard with `pbpaste` in a UTF-8 locale, preserving characters such as `žćđš`. `-c`/`--clipboard` remains an alias for this behavior. The client never copies a selection; the hotkey handles that before starting it.

Use `-g`/`--toggle` on a hotkey. If speech is playing or still being prepared, it stops. Otherwise it reads the clipboard, or the text supplied with `-t`. You can combine it with `-v` to choose a voice. Do not combine it with `-s` or `-l`. Toggle requires the server version with the `status` command; rebuild and restart the server when upgrading from an older version.

## Global shortcuts

For Edge TTS, add these bindings to `~/.config/skhd/skhdrc`:

```text
ctrl + alt - q : /bin/sh -c 'sleep 0.3; /opt/homebrew/bin/skhd -k "cmd - c" && sleep 0.2 && "$HOME/tts/tts-client" -g -v en-US-AndrewNeural' >> "$HOME/tts/tts-hotkeys.log" 2>&1
ctrl + alt - w : /bin/sh -c 'sleep 0.3; /opt/homebrew/bin/skhd -k "cmd - c" && sleep 0.2 && "$HOME/tts/tts-client" -g -v hr-HR-GabrijelaNeural' >> "$HOME/tts/tts-hotkeys.log" 2>&1
ctrl + alt - e : "$HOME/tts/tts-client" -s >> "$HOME/tts/tts-hotkeys.log" 2>&1
```

Control-Option-Q and Control-Option-W pause briefly to allow the shortcut keys to be released, copy the selection with `skhd`, then start reading with their chosen voice when idle or stop the current reading. Either key can stop speech started by the other. Control-Option-E is an optional dedicated stop key. The copy step also runs when a toggle key stops speech.

The repository [`skhdrc`](skhdrc) has these Edge TTS bindings enabled. It also keeps the separate Croatian voice experiment commented out. Install `skhd` and place your chosen bindings in its config:

```bash
brew install jackielii/tap/skhd-zig
mkdir -p ~/.config/skhd
skhd --start-service
```

Grant `skhd` Accessibility permission in System Settings → Privacy & Security. macOS may also request Input Monitoring. After changing bindings, run `skhd -r`; after changing `client.sh`, reinstall it with `install -m 755 client.sh ~/tts/tts-client`. If `skhd --start-service` reports that it cannot find its bundled plist, run the command from the installed `skhd.app/Contents/MacOS/skhd` executable instead.

## Troubleshooting

Client errors go to `~/tts/tts-client.log`; skhd command output goes to `~/tts/tts-hotkeys.log`; server errors go to `~/tts/tts-server.log`. Successful read and stop requests are silent; `-l` prints the voice list. Run `~/tts/tts-server.dist/tts-server` in a terminal to see startup errors directly. If a hotkey does nothing, check the logs and skhd's Accessibility permission.
