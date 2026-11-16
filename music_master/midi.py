from __future__ import annotations

import re
import struct
from pathlib import Path

from .models import MidiNote, Track


def transpose(track: Track, semitones: int) -> None:
    for note in track.notes:
        note.pitch = max(0, min(127, note.pitch + semitones))


def quantize(track: Track, subdivision: float = 0.5) -> None:
    if subdivision <= 0:
        return
    for note in track.notes:
        note.start = round(note.start / subdivision) * subdivision


def write_midi(track: Track, path: Path, tempo: int = 100) -> None:
    """Escribe un MIDI tipo 0 mínimo, sin depender de una librería externa."""
    ppq = 480
    events: list[tuple[int, bytes]] = []
    for note in track.notes:
        start = max(0, round(note.start * ppq))
        end = max(start + 1, round((note.start + note.duration) * ppq))
        events.append((start, bytes([0x90 | note.channel, note.pitch, max(1, min(127, note.velocity))])))
        events.append((end, bytes([0x80 | note.channel, note.pitch, 0])))
    events.sort(key=lambda x: (x[0], x[1][0] & 0xF0 == 0x80))
    body = bytearray()
    last = 0
    for tick, message in events:
        body.extend(_vlq(max(0, tick - last)))
        body.extend(message)
        last = tick
    body.extend(_vlq(0) + b"\xff\x2f\x00")
    track_chunk = b"MTrk" + struct.pack(">I", len(body)) + body
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppq)
    path.write_bytes(header + track_chunk)


def _vlq(value: int) -> bytes:
    buffer = value & 0x7F
    out = bytearray()
    while value > 0x7F:
        value >>= 7
        buffer <<= 8
        buffer |= (value & 0x7F) | 0x80
    while True:
        out.append(buffer & 0xFF)
        if buffer & 0x80:
            buffer >>= 8
        else:
            break
    return bytes(out)


def parse_action(prompt: str) -> tuple[str, int | float | str] | None:
    text = prompt.lower().strip()
    match = re.search(r"duplic(?:a|ar)\s+(?:el\s+)?(?:fragmento\s+)?(.+)$", text)
    if match:
        return "duplicate_fragment", match.group(1).strip().strip('"\'')
    match = re.search(r"(?:transport|subi|baj[aá]|mover).*?(-?\d+)\s*semiton", text)
    if match:
        return "transpose", int(match.group(1))
    if "tercera menor" in text:
        return "transpose", 3
    if "tercera mayor" in text:
        return "transpose", 4
    match = re.search(r"tempo.*?(\d{2,3})", text)
    if match:
        return "tempo", int(match.group(1))
    if "cuant" in text:
        return "quantize", 0.5 if "corche" in text else 1.0
    return None


def read_midi_notes(path: Path) -> list[MidiNote]:
    """Lee notas de un MIDI usando mido, que es opcional."""
    try:
        import mido
    except ImportError as exc:
        raise RuntimeError("Instalá mido para importar el MIDI generado") from exc
    midi = mido.MidiFile(str(path))
    notes: dict[tuple[int, int], tuple[float, int]] = {}
    active_time = 0.0
    result: list[MidiNote] = []
    for message in midi.merged_track:
        active_time += message.time / midi.ticks_per_beat
        if message.type == "note_on" and message.velocity > 0:
            notes[(message.channel, message.note)] = (active_time, message.velocity)
        elif message.type in ("note_off", "note_on"):
            key = (message.channel, message.note)
            if key in notes:
                start, velocity = notes.pop(key)
                result.append(MidiNote(message.note, start, max(0.05, active_time - start), velocity, message.channel))
    return sorted(result, key=lambda note: note.start)

