"""
Real-time voice input service.

Design goals:
- Non-blocking for simulation loop
- Separate worker thread for microphone listening
- Graceful fallback if speech libraries are unavailable
"""

import queue
import threading
import time


class VoiceController:
    def __init__(self):
        self._result_queue = queue.Queue()
        self._listen_requests = queue.Queue()
        self._tts_queue = queue.Queue()
        self._stop_event = threading.Event()

        self._sr = None
        self._recognizer = None
        self._tts_engine = None
        self._voice_enabled = False
        self._tts_enabled = False
        self._busy = False
        self._backend_name = "none"
        self._device_indices = []
        self._sd = None
        self._np = None
        self._use_sounddevice_fallback = False

        self._setup_voice_backend()
        self._setup_tts_backend()

        self._listen_thread = threading.Thread(target=self._listen_worker, daemon=True)
        self._listen_thread.start()
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

    def request_listen(self):
        """
        Queue one microphone listening action.
        Called by main thread (e.g., SPACE key).
        """
        if self._busy:
            self._result_queue.put(
                {
                    "type": "voice_status",
                    "ok": True,
                    "message": "Already listening...",
                }
            )
            return
        self._listen_requests.put(True)

    def poll_results(self):
        """
        Non-blocking pull of recognized speech events.
        """
        results = []
        while True:
            try:
                results.append(self._result_queue.get_nowait())
            except queue.Empty:
                break
        return results

    def speak(self, text):
        """
        Optional TTS output in a background thread.
        """
        if not self._tts_enabled:
            return
        self._tts_queue.put(str(text))

    def shutdown(self):
        self._stop_event.set()
        self._listen_requests.put(False)
        self._tts_queue.put(None)
        time.sleep(0.05)

    def _setup_voice_backend(self):
        try:
            import speech_recognition as sr

            self._sr = sr
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = 250
            self._recognizer.dynamic_energy_threshold = True
            self._voice_enabled = True
            self._backend_name = "speech_recognition"
            self._device_indices = self._discover_devices(sr)
            self._setup_sounddevice_fallback()
            self._result_queue.put(
                {
                    "type": "voice_status",
                    "ok": True,
                    "message": "Voice backend ready. Press SPACE and speak.",
                }
            )
        except Exception as exc:  # pragma: no cover
            self._voice_enabled = False
            self._result_queue.put(
                {
                    "type": "voice_status",
                    "ok": False,
                    "message": (
                        "Voice backend unavailable. Install: "
                        "speechrecognition + (pyaudio OR sounddevice+numpy). "
                        f"Details: {exc}"
                    ),
                }
            )

    def _discover_devices(self, sr):
        """
        Cache microphone indices so we can fallback if default device fails.
        """
        indices = [None]  # None means OS default device.
        try:
            names = sr.Microphone.list_microphone_names()
            for idx, _ in enumerate(names):
                indices.append(idx)
        except Exception:
            # Keep default device fallback even if listing fails.
            pass
        return indices

    def _setup_sounddevice_fallback(self):
        """
        Optional fallback path when PyAudio/Microphone backend is unavailable.
        """
        try:
            import sounddevice as sd
            import numpy as np

            self._sd = sd
            self._np = np
            self._use_sounddevice_fallback = True
        except Exception:
            self._use_sounddevice_fallback = False

    def _setup_tts_backend(self):
        try:
            import pyttsx3

            self._tts_engine = pyttsx3.init()
            self._tts_engine.setProperty("rate", 175)
            self._tts_enabled = True
        except Exception:
            self._tts_enabled = False

    def _listen_worker(self):
        while not self._stop_event.is_set():
            try:
                self._listen_requests.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._stop_event.is_set():
                break

            if not self._voice_enabled:
                self._result_queue.put(
                    {
                        "type": "voice_error",
                        "message": (
                            "Voice recognition is not available. "
                            "Install speechrecognition and either pyaudio or sounddevice+numpy, then restart."
                        ),
                    }
                )
                continue

            try:
                self._busy = True
                self._result_queue.put({"type": "voice_listening", "message": "Listening..."})
                audio = self._listen_from_any_device()
                text = self._recognize_audio(audio)
                self._result_queue.put({"type": "voice_text", "text": text})
            except self._sr.WaitTimeoutError:
                self._result_queue.put(
                    {
                        "type": "voice_error",
                        "message": "No speech detected in time.",
                    }
                )
            except self._sr.UnknownValueError:
                self._result_queue.put(
                    {
                        "type": "voice_error",
                        "message": "Sorry, I didn't understand.",
                    }
                )
            except Exception as exc:
                self._result_queue.put(
                    {
                        "type": "voice_error",
                        "message": f"Voice recognition failed: {exc}. Check mic permission/device.",
                    }
                )
            finally:
                self._busy = False

    def _listen_from_any_device(self):
        """
        Try PyAudio-backed microphone first, then sounddevice fallback.
        """
        last_error = None
        for device_index in self._device_indices:
            try:
                with self._sr.Microphone(device_index=device_index) as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=0.25)
                    return self._recognizer.listen(source, timeout=4, phrase_time_limit=7)
            except Exception as exc:
                last_error = exc
                continue
        if self._use_sounddevice_fallback:
            return self._listen_with_sounddevice()
        if last_error is not None:
            raise last_error
        raise RuntimeError("No microphone device available.")

    def _listen_with_sounddevice(self):
        """
        Microphone capture fallback (no PyAudio needed).

        We record a short clip and convert it into SpeechRecognition AudioData.
        """
        samplerate = 16000
        duration_sec = 5.0
        frames = int(samplerate * duration_sec)

        data = self._sd.rec(frames, samplerate=samplerate, channels=1, dtype="int16")
        self._sd.wait()

        # Basic silence check so we can return a friendly timeout-like error.
        peak = int(self._np.max(self._np.abs(data))) if data.size else 0
        if peak < 80:
            raise self._sr.WaitTimeoutError("Very low input volume / silence.")

        raw_bytes = data.tobytes()
        return self._sr.AudioData(raw_bytes, samplerate, 2)

    def _recognize_audio(self, audio):
        """
        Recognition strategy:
        1) Google recognizer (best quality, needs internet)
        2) Sphinx recognizer (offline if installed)
        """
        try:
            return self._recognizer.recognize_google(audio)
        except Exception:
            try:
                return self._recognizer.recognize_sphinx(audio)
            except Exception:
                raise self._sr.UnknownValueError()

    def _tts_worker(self):
        while not self._stop_event.is_set():
            try:
                item = self._tts_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None or self._stop_event.is_set():
                break
            if not self._tts_enabled:
                continue
            try:
                self._tts_engine.say(item)
                self._tts_engine.runAndWait()
            except Exception:
                # Keep simulation stable even if TTS fails.
                pass
