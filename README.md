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

## Use the client

```bash
~/tts/tts-client                          # Copy and read selected text
~/tts/tts-client -t "Hello"               # Read supplied text
~/tts/tts-client -c                       # Read existing clipboard text (--clipboard also works)
~/tts/tts-client -v hr-HR-GabrijelaNeural # Change voice
~/tts/tts-client --no-clean               # Skip text cleaning
~/tts/tts-client -g                       # Toggle: stop, or copy and read selection
~/tts/tts-client -g -v hr-HR-GabrijelaNeural # Toggle with a Croatian voice
~/tts/tts-client -s                       # Stop playback
~/tts/tts-client -l                       # List available voices
```

With no text argument, the client waits for the shortcut keys to be released, sends Command-C to the active app, then waits for the clipboard to update. When `skhd` is on `PATH`, it sends Command-C with `skhd -k`; otherwise it uses System Events, which may require Accessibility and Automation permission. `-t`, `-c`/`--clipboard`, `-s`, and `-l` do not copy a selection.

Use `-g`/`--toggle` on a hotkey. If speech is playing or still being prepared, it stops without copying text. Otherwise it starts reading, copying the current selection unless `-t` or `-c` supplies text. You can combine it with `-v` to choose a voice. Do not combine it with `-s` or `-l`. Toggle requires the server version with the `status` command; rebuild and restart the server when upgrading from an older version.

## Global shortcuts

For Edge TTS, add these bindings to `~/.config/skhd/skhdrc`:

```text
ctrl + alt - q : "$HOME/tts/tts-client" -g -v en-US-AndrewNeural >> "$HOME/tts/tts-hotkeys.log" 2>&1
ctrl + alt - w : "$HOME/tts/tts-client" -g -v hr-HR-GabrijelaNeural >> "$HOME/tts/tts-hotkeys.log" 2>&1
ctrl + alt - e : "$HOME/tts/tts-client" -s >> "$HOME/tts/tts-hotkeys.log" 2>&1
```

Control-Option-Q and Control-Option-W each start reading with their chosen voice when idle and stop the current reading when pressed again. Either key can stop speech started by the other. Control-Option-E is an optional dedicated stop key.

The repository [`skhdrc`](skhdrc) currently has the Edge TTS lines commented out and uses Control-Option-W/E for a separate Croatian voice experiment. To use the Edge TTS bindings above, remove or comment out the conflicting W/E lines in that sample. Install `skhd` and place your chosen bindings in its config:

```bash
brew install jackielii/tap/skhd-zig
mkdir -p ~/.config/skhd
skhd --start-service
```

Grant `skhd` Accessibility permission in System Settings → Privacy & Security. macOS may also request Input Monitoring. After changing bindings, run `skhd -r`; after changing `client.sh`, reinstall it with `install -m 755 client.sh ~/tts/tts-client`. If `skhd --start-service` reports that it cannot find its bundled plist, run the command from the installed `skhd.app/Contents/MacOS/skhd` executable instead.

## Troubleshooting

Client errors go to `~/tts/tts-client.log`; skhd command output goes to `~/tts/tts-hotkeys.log`; server errors go to `~/tts/tts-server.log`. Successful read and stop requests are silent; `-l` prints the voice list. Run `~/tts/tts-server.dist/tts-server` in a terminal to see startup errors directly. If a hotkey does nothing, check the logs and skhd's Accessibility permission. An `osascript is not allowed to send keystrokes` error means the client used the System Events fallback; check that `skhd` is installed and on `PATH`.
