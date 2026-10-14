#!/bin/bash

# Install this macOS client as ~/tts/tts-client beside a built tts-server.

PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH

SOCKET_PATH="/tmp/enge_tts.sock"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_BIN="$SCRIPT_DIR/tts-server.dist/tts-server"
LEGACY_SERVER_BIN="$SCRIPT_DIR/tts-server"
SERVER_LOG="$SCRIPT_DIR/tts-server.log"
CLIENT_LOG="$SCRIPT_DIR/tts-client.log"
DEFAULT_VOICE="en-US-EmmaNeural"
PYTHON_BIN="/usr/bin/python3"

notify_error() {
    echo "Error: $1" >&2
    printf '%s - Error: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >>"$CLIENT_LOG" 2>/dev/null || true
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        notify_error "Required command '$1' was not found."
        exit 1
    fi
}

start_server() {
    if [ -x "$SERVER_BIN" ]; then
        SERVER_PATH="$SERVER_BIN"
    elif [ -x "$LEGACY_SERVER_BIN" ]; then
        SERVER_PATH="$LEGACY_SERVER_BIN"
    elif command -v tts-server >/dev/null 2>&1; then
        SERVER_PATH="tts-server"
    else
        notify_error "Server was not found in tts-server.dist, beside this client, or on PATH."
        exit 1
    fi

    nohup "$SERVER_PATH" >>"$SERVER_LOG" 2>&1 &

    local retries=50
    while [ "$retries" -gt 0 ]; do
        if [ -S "$SOCKET_PATH" ]; then
            return 0
        fi
        sleep 0.1
        retries=$((retries - 1))
    done

    notify_error "Timed out waiting for tts-server to start."
    exit 1
}

ensure_server_running() {
    if [ ! -S "$SOCKET_PATH" ]; then
        start_server
    fi
}

socket_request() {
    printf '%s' "$JSON_PAYLOAD" | "$PYTHON_BIN" -c '
import socket
import sys

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.settimeout(float(sys.argv[2]))
    connection.connect(sys.argv[1])
    connection.sendall(sys.stdin.buffer.read())
    connection.shutdown(socket.SHUT_WR)
    while True:
        chunk = connection.recv(65536)
        if not chunk:
            break
        sys.stdout.buffer.write(chunk)
' "$SOCKET_PATH" "$TIMEOUT"
}

send_request() {
    RESPONSE=$(socket_request 2>/dev/null)
    REQUEST_STATUS=$?

    if [ "$REQUEST_STATUS" -ne 0 ]; then
        start_server
        local retries=50
        while [ "$retries" -gt 0 ]; do
            RESPONSE=$(socket_request 2>/dev/null)
            REQUEST_STATUS=$?
            if [ "$REQUEST_STATUS" -eq 0 ]; then
                break
            fi
            sleep 0.1
            retries=$((retries - 1))
        done
    fi

    if [ "$REQUEST_STATUS" -ne 0 ]; then
        notify_error "Could not communicate with tts-server."
        exit "$REQUEST_STATUS"
    fi

    case "$RESPONSE" in
        Error*|"Server Error"*|"Invalid JSON"|"Unknown command")
            printf '%s\n' "$RESPONSE" >&2
            exit 1
            ;;
    esac

    if [ "$LIST" = true ]; then
        printf '%s\n' "$RESPONSE"
    fi
}

TEXT=""
STOP=false
LIST=false
TOGGLE=false
VOICE="$DEFAULT_VOICE"
CLEAN=true

while [ "$#" -gt 0 ]; do
    case "$1" in
        -t|--text)
            if [ "$#" -lt 2 ]; then
                notify_error "Missing text after $1."
                exit 1
            fi
            TEXT="$2"
            shift
            ;;
        -s|--stop)
            STOP=true
            ;;
        -g|--toggle)
            TOGGLE=true
            ;;
        -l|--list-voices)
            LIST=true
            ;;
        -v|--voice)
            if [ "$#" -lt 2 ]; then
                notify_error "Missing voice after $1."
                exit 1
            fi
            VOICE="$2"
            shift
            ;;
        --no-clean)
            CLEAN=false
            ;;
        -c|--clipboard)
            ;;
        *)
            notify_error "Unknown parameter: $1"
            exit 1
            ;;
    esac
    shift
done

require_command jq
require_command "$PYTHON_BIN"

if [ "$TOGGLE" = true ]; then
    if [ "$STOP" = true ] || [ "$LIST" = true ]; then
        notify_error "--toggle cannot be combined with --stop or --list-voices."
        exit 1
    fi
    JSON_PAYLOAD=$(jq -n '{command: "status"}')
    TIMEOUT=2
    ensure_server_running
    send_request
    case "$RESPONSE" in
        Reading) STOP=true ;;
        Idle) ;;
        *)
            notify_error "Unexpected server status: $RESPONSE"
            exit 1
            ;;
    esac
fi

if [ "$STOP" = true ]; then
    JSON_PAYLOAD=$(jq -n --arg cmd "stop" '{command: $cmd}')
    TIMEOUT=2
elif [ "$LIST" = true ]; then
    JSON_PAYLOAD=$(jq -n --arg cmd "list_voices" '{command: $cmd}')
    TIMEOUT=10
else
    if [ -z "$TEXT" ]; then
        if ! TEXT=$(LC_ALL=en_US.UTF-8 pbpaste 2>/dev/null); then
            notify_error "Could not read text from the clipboard."
            exit 1
        fi
    fi

    if [ -z "$TEXT" ]; then
        notify_error "No text was supplied."
        exit 1
    fi

    JSON_PAYLOAD=$(jq -n \
        --arg cmd "read" \
        --arg txt "$TEXT" \
        --arg vc "$VOICE" \
        --argjson cl "$CLEAN" \
        '{command: $cmd, text: $txt, voice: $vc, clean: $cl}')
    TIMEOUT=30
fi

ensure_server_running
send_request
