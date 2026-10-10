#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# server.py

import asyncio
import fcntl
import json
import logging
import os
import re
import setproctitle
import aiohttp
import edge_tts
import miniaudio
from miniaudio import SampleFormat
import cleantext
from playback import WaveObject

# --- Config ---
SOCKET_PATH = "/tmp/mac_tts_reader.sock"
PROCESS_NAME = "mac-tts-reader-server"
DEFAULT_VOICE = "en-US-EmmaNeural"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - SERVER - %(message)s",
    datefmt="%H:%M:%S",
)


class TTSPlayer:
    def __init__(self, text: str, voice: str):
        self.voice = voice
        self.sentences = self._split_and_merge_sentences(text)
        self._current_play_obj = None
        self._stop_event = asyncio.Event()

    def _split_and_merge_sentences(self, text: str, min_words_to_merge: int = 6):
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if not sentences: return []
        merged = []
        i = 0
        while i < len(sentences):
            curr = sentences[i].strip()
            if not curr:
                i += 1; continue
            if len(curr.split()) < min_words_to_merge and (i + 1) < len(sentences):
                next_s = sentences[i + 1].strip()
                if next_s: merged.append(curr + " " + next_s); i += 2
                else: merged.append(curr); i += 2
            else:
                merged.append(curr); i += 1
        return [s for s in merged if s]

    async def _synthesize_sentence(self, sentence: str):
        attempts = 4
        for attempt in range(attempts):
            communicate = edge_tts.Communicate(sentence, self.voice)
            audio_bytes = b""
            try:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes += chunk["data"]
                break
            except aiohttp.ClientResponseError as error:
                if error.status not in (403, 429, 503) or attempt == attempts - 1:
                    raise RuntimeError(
                        f"Speech service returned HTTP {error.status} after {attempt + 1} attempt(s)."
                    ) from error
                logging.warning(
                    "Speech service returned HTTP %s; retrying synthesis (%s/%s).",
                    error.status, attempt + 1, attempts,
                )
                await asyncio.sleep(0.5 * (2 ** attempt))
        
        audio_data = miniaudio.decode(audio_bytes, output_format=SampleFormat.SIGNED16)
        samples = audio_data.samples.tobytes()
        return WaveObject(
            samples,
            audio_data.nchannels,
            audio_data.sample_width,
            audio_data.sample_rate,
        )

    def stop(self):
        """Signal the player to stop."""
        self._stop_event.set()
        if self._current_play_obj and self._current_play_obj.is_playing():
            self._current_play_obj.stop()

    async def run(self, ready=None):
        if not self.sentences: return
        loop = asyncio.get_running_loop()
        
        try:
            # Pre-buffer first sentence
            current_wave = await self._synthesize_sentence(self.sentences[0])
            next_task = None
            
            if len(self.sentences) > 1:
                next_task = asyncio.create_task(self._synthesize_sentence(self.sentences[1]))

            self._current_play_obj = current_wave.play()
            if ready is not None and not ready.done():
                ready.set_result(None)
            
            for i in range(1, len(self.sentences)):
                if self._stop_event.is_set(): break
                
                # Wait for current audio to finish
                await loop.run_in_executor(None, self._current_play_obj.wait_done)
                
                if self._stop_event.is_set(): break

                current_wave = await next_task
                if i + 1 < len(self.sentences):
                    next_task = asyncio.create_task(self._synthesize_sentence(self.sentences[i + 1]))
                
                self._current_play_obj = current_wave.play()

            if self._current_play_obj and not self._stop_event.is_set():
                await loop.run_in_executor(None, self._current_play_obj.wait_done)

        except asyncio.CancelledError:
            if ready is not None and not ready.done():
                ready.cancel()
            raise
        except Exception as e:
            if ready is not None and not ready.done():
                ready.set_exception(e)
            logging.error(f"Playback error: {e}")
        finally:
            logging.info("Playback finished or stopped.")

class TTSServer:
    def __init__(self):
        self.current_player_task = None
        self.current_player = None

    def clean_text(self, text):
        return cleantext.clean(
            text, extra_spaces=True, lowercase=False, numbers=False, punct=False, reg=r'\[.*?\]'
        )

    async def handle_client(self, reader, writer):
        data = await reader.read(100000) # Read up to 100KB
        message = data.decode()
        addr = writer.get_extra_info('peername')
        logging.info(f"Received request from {addr}")

        try:
            request = json.loads(message)
            command = request.get('command')

            if command == 'stop':
                await self.stop_playback()
                response = "Stopped"
            
            elif command == 'read':
                # 1. Stop existing
                await self.stop_playback()
                
                # 2. Process new
                text = request.get('text', '')
                voice = request.get('voice', DEFAULT_VOICE)
                clean = request.get('clean', True)
                
                if clean:
                    text = self.clean_text(text)
                
                # 3. Start new
                self.current_player = TTSPlayer(text, voice)
                ready = asyncio.get_running_loop().create_future()
                self.current_player_task = asyncio.create_task(self.current_player.run(ready))
                try:
                    await ready
                    response = "Reading started"
                except asyncio.CancelledError:
                    response = "Error: Reading was stopped before playback began."
                except Exception as error:
                    response = f"Error: {error}"

            elif command == 'list_voices':
                try:
                    voices = await edge_tts.list_voices()
                    # Format: "ShortName (Gender)"
                    voice_list = "\n".join(
                        [f"{v['ShortName']} ({v['Gender']})" for v in sorted(voices, key=lambda x: x['ShortName'])]
                    )
                    response = voice_list
                except Exception as e:
                    response = f"Error fetching voices: {e}"

            else:
                response = "Unknown command"

        except json.JSONDecodeError:
            response = "Invalid JSON"
        except Exception as e:
            logging.error(f"Error handling request: {e}")
            response = f"Server Error: {str(e)}"

        logging.info(f"Response: {response}")
        try:
            writer.write(response.encode())
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            logging.warning("Client disconnected before response was fully sent (not critical).")
        except Exception as e:
            logging.error(f"Network write error: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass # Socket already dead, ignore        

    async def stop_playback(self):
        if self.current_player:
            self.current_player.stop()
        if self.current_player_task:
            self.current_player_task.cancel()
            try:
                await self.current_player_task
            except asyncio.CancelledError:
                pass
        self.current_player = None
        self.current_player_task = None

    async def run_server(self):
        lock_fd = os.open(SOCKET_PATH + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(lock_fd)
            logging.info("Server is already running.")
            return

        try:
            if os.path.exists(SOCKET_PATH):
                os.remove(SOCKET_PATH)

            server = await asyncio.start_unix_server(self.handle_client, path=SOCKET_PATH)
            logging.info(f"Serving on {SOCKET_PATH}")

            async with server:
                await server.serve_forever()
        finally:
            os.close(lock_fd)

if __name__ == "__main__":
    setproctitle.setproctitle(PROCESS_NAME)
    # Handle Ctrl+C gracefully
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tts_server = TTSServer()
    try:
        loop.run_until_complete(tts_server.run_server())
    except KeyboardInterrupt:
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
