# mac-tts-reader

Read selected text aloud on macOS with Microsoft Edge neural voices. A local Python server stays running between requests, synthesizes speech through Edge TTS, and plays it from memory. The Bash client connects over `/tmp/mac_tts_reader.sock` and starts the server when needed.

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

mkdir -p ~/mac-tts-reader
cp -R tts-server.dist ~/mac-tts-reader/
install -m 755 client.sh ~/mac-tts-reader/tts-client
```

After rebuilding, replace the installed `~/mac-tts-reader/tts-server.dist` and restart the running server. The client starts `~/mac-tts-reader/tts-server.dist/tts-server` automatically when no server is available. Nuitka's `--onefile` mode can fail macOS code-signature checks, so use the standalone build shown here.

## Use the client

```bash
~/mac-tts-reader/tts-client                          # Copy and read selected text
~/mac-tts-reader/tts-client -t "Hello"               # Read supplied text
~/mac-tts-reader/tts-client --clipboard              # Read existing clipboard text
~/mac-tts-reader/tts-client -v hr-HR-GabrijelaNeural # Change voice
~/mac-tts-reader/tts-client --no-clean               # Skip text cleaning
~/mac-tts-reader/tts-client -s                       # Stop playback
~/mac-tts-reader/tts-client -l                       # List available voices
```

The default action sends Command-C to the active app and requires Accessibility permission for the terminal or shortcut service. `-t`, `--clipboard`, `-s`, and `-l` do not copy a selection.

## Global shortcuts

The sample [`skhdrc`](skhdrc) binds Control-Option-Q to English, Control-Option-W to Croatian, and Control-Option-E to stop. Install `skhd`, then copy or merge the sample bindings:

```bash
brew install jackielii/tap/skhd-zig
mkdir -p ~/.config/skhd
cp -n skhdrc ~/.config/skhd/skhdrc
skhd --start-service
```

Grant `skhd` Accessibility permission in System Settings → Privacy & Security. macOS may also request Input Monitoring. After changing permissions or bindings, run `skhd --restart-service`. Change a voice by editing its `-v` value in `~/.config/skhd/skhdrc`; use `~/mac-tts-reader/tts-client -l` to find voice IDs.

## Troubleshooting

Client errors go to `~/mac-tts-reader/tts-client.log`; server startup and playback errors go to `~/mac-tts-reader/tts-server.log`. Run `~/mac-tts-reader/tts-server.dist/tts-server` in a terminal to see startup errors directly. If a shortcut does nothing, check `~/Library/Logs/skhd.log` and the app permissions above.
