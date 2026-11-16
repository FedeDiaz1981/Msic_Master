from __future__ import annotations

import subprocess
import sys
import wave
import os
import threading
from pathlib import Path


def record_wav(path: Path, seconds: float = 10, sample_rate: int = 44100) -> None:
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Instalá sounddevice y soundfile para grabar desde el micrófono") from exc
    recording = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    sf.write(str(path), recording, sample_rate, subtype="PCM_24")


def record_until_stopped(path: Path, stop_event: threading.Event, sample_rate: int = 44100) -> None:
    """Graba desde el micrÃ³fono hasta que el modal indique detener."""
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("InstalÃ¡ sounddevice, soundfile y numpy para grabar") from exc
    chunks = []

    def callback(indata, frames, time, status):
        if status:
            pass
        chunks.append(indata.copy())
        if stop_event.is_set():
            raise sd.CallbackStop()

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32", callback=callback):
        while not stop_event.is_set():
            stop_event.wait(0.05)
    data = np.concatenate(chunks, axis=0) if chunks else np.zeros((1, 1), dtype="float32")
    sf.write(str(path), data, sample_rate, subtype="PCM_24")


def trim_audio(source: Path, target: Path, start_seconds: float, end_seconds: float) -> None:
    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("InstalÃ¡ soundfile para recortar audio") from exc
    data, rate = sf.read(str(source), dtype="float32", always_2d=True)
    start = max(0, int(start_seconds * rate))
    end = min(len(data), int(end_seconds * rate))
    if end <= start:
        raise ValueError("El final del recorte debe ser posterior al inicio")
    sf.write(str(target), data[start:end], rate, subtype="PCM_24")


def play_audio(path: Path) -> None:
    """Reproduce una guÃ­a de audio y espera hasta que termine."""
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("InstalÃ¡ sounddevice y soundfile para reproducir audio") from exc
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    sd.play(data, rate)
    sd.wait()


def play_audio_segment(path: Path, start_seconds: float, end_seconds: float) -> None:
    """Reproduce solamente el rango seleccionado de un audio."""
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("InstalÃ¡ sounddevice y soundfile para reproducir audio") from exc
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    start = max(0, int(start_seconds * rate))
    end = min(len(data), int(end_seconds * rate))
    if end <= start:
        raise ValueError("El rango seleccionado no es vÃ¡lido")
    sd.play(data[start:end], rate)
    sd.wait()


def synthesize_midi_tracks(tracks, tempo: int, sample_rate: int = 44100):
    """Genera una preescucha sencilla de varias pistas MIDI en memoria.

    Es una referencia sonora para editar el proyecto; los VST se conectarÃ¡n
    posteriormente para obtener sonidos realistas.
    """
    import numpy as np

    active = [track for track in tracks if track.kind == "midi" and track.notes and not track.muted]
    if not active:
        raise ValueError("No hay pistas MIDI activas con notas")
    seconds_per_beat = 60.0 / max(1, tempo)
    total_beats = max(note.start + note.duration for track in active for note in track.notes)
    output = np.zeros((max(1, int((total_beats * seconds_per_beat + 0.5) * sample_rate)), 2), dtype=np.float32)
    instrument_brightness = {
        "Bajo": 0.65, "Piano": 1.0, "Guitarra": 0.85, "Voz / tarareo": 0.9,
        "ViolÃ­n": 1.15, "Flauta": 1.2, "SaxofÃ³n": 0.95,
    }
    for track in active:
        brightness = instrument_brightness.get(track.instrument or "", 1.0)
        for note in track.notes:
            start = int(note.start * seconds_per_beat * sample_rate)
            length = max(1, int(note.duration * seconds_per_beat * sample_rate))
            end = min(len(output), start + length)
            if start >= end:
                continue
            t = np.arange(end - start, dtype=np.float32) / sample_rate
            frequency = 440.0 * (2.0 ** ((note.pitch - 69) / 12.0))
            wave_data = np.sin(2 * np.pi * frequency * t)
            wave_data += 0.25 * np.sin(2 * np.pi * frequency * 2 * t) * brightness
            attack = np.minimum(1.0, t * 80.0)
            release = np.minimum(1.0, (len(wave_data) - np.arange(len(wave_data))) / (sample_rate * 0.04))
            envelope = np.minimum(attack, release)
            amplitude = min(0.25, max(0.03, note.velocity / 1270.0))
            output[start:end, 0] += wave_data * envelope * amplitude
            output[start:end, 1] += wave_data * envelope * amplitude
    return np.clip(output, -1.0, 1.0), sample_rate


def render_guides_to_wav(paths: list[Path], output: Path) -> None:
    """Mezcla guías WAV de igual formato; MP3 requiere conversión externa."""
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Instalá numpy y soundfile para renderizar WAV") from exc
    buffers = []
    rate = None
    for path in paths:
        data, current_rate = sf.read(str(path), always_2d=True, dtype="float32")
        rate = rate or current_rate
        if current_rate != rate:
            raise ValueError("Las guías deben tener la misma frecuencia de muestreo")
        buffers.append(data)
    if not buffers:
        raise ValueError("No hay audios para mezclar")
    length = max(len(item) for item in buffers)
    channels = max(item.shape[1] for item in buffers)
    mix = np.zeros((length, channels), dtype="float32")
    for item in buffers:
        expanded = item if item.shape[1] == channels else np.repeat(item, channels, axis=1)
        mix[: len(expanded)] += expanded / len(buffers)
    sf.write(str(output), np.clip(mix, -1, 1), rate, subtype="PCM_24")


def transcribe_to_midi(
    audio_path: Path,
    output_dir: Path,
    tempo: int = 100,
    minimum_frequency: float | None = None,
    maximum_frequency: float | None = None,
) -> Path:
    """Convierte una guía a MIDI usando Basic Pitch instalado en el mismo Python."""
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "basic_pitch.predict",
        str(output_dir),
        str(audio_path),
        "--save-note-events",
        "--midi-tempo",
        str(tempo),
    ]
    if minimum_frequency is not None:
        command.extend(["--minimum-frequency", str(minimum_frequency)])
    if maximum_frequency is not None:
        command.extend(["--maximum-frequency", str(maximum_frequency)])
    # Basic Pitch puede imprimir símbolos Unicode (por ejemplo, flechas) en sus
    # advertencias. En Windows, el proceso puede heredar una consola con cp1252
    # y fallar antes de terminar el análisis. Forzamos UTF-8 también dentro del
    # proceso hijo y reemplazamos cualquier carácter problemático al capturarlo.
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError("Basic Pitch no pudo convertir el audio.\n" + details[-2000:])
    candidates = sorted(output_dir.glob(f"{audio_path.stem}*.mid"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError("Basic Pitch terminó pero no generó un archivo MIDI")
    return candidates[0]

