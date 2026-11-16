from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class MidiNote:
    pitch: int
    start: float
    duration: float = 0.5
    velocity: int = 90
    channel: int = 0


@dataclass
class MidiFragment:
    id: str
    name: str
    start: float = 0.0
    notes: list[MidiNote] = field(default_factory=list)

    @property
    def duration(self) -> float:
        if not self.notes:
            return 0.0
        return max(note.start + note.duration for note in self.notes) - self.start


@dataclass
class Track:
    id: str
    name: str
    kind: str = "guide"  # guide, midi, audio
    source: str | None = None
    instrument: str | None = None
    notes: list[MidiNote] = field(default_factory=list)
    fragments: list[MidiFragment] = field(default_factory=list)
    muted: bool = False


@dataclass
class Project:
    name: str
    root: str
    tempo: int = 100
    time_signature: str = "4/4"
    tracks: list[Track] = field(default_factory=list)

    @classmethod
    def create(cls, folder: Path, name: str = "Nuevo proyecto") -> "Project":
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "audio").mkdir(exist_ok=True)
        (folder / "midi").mkdir(exist_ok=True)
        (folder / "renders").mkdir(exist_ok=True)
        return cls(name=name, root=str(folder.resolve()))

    @classmethod
    def load(cls, path: Path) -> "Project":
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tracks"] = [
            Track(
                **{
                    **track,
                    "notes": [MidiNote(**n) for n in track.get("notes", [])],
                    "fragments": [
                        MidiFragment(
                            **{
                                **fragment,
                                "notes": [MidiNote(**n) for n in fragment.get("notes", [])],
                            }
                        )
                        for fragment in track.get("fragments", [])
                    ],
                }
            )
            for track in data.get("tracks", [])
        ]
        for track in data["tracks"]:
            if track.kind == "midi" and not track.fragments and track.notes:
                track.fragments = [MidiFragment(uuid.uuid4().hex[:8], "Fragmento original", 0.0, track.notes)]
        return cls(**data)

    def save(self) -> Path:
        path = Path(self.root) / "project.json"
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def add_track(self, name: str, kind: str = "guide") -> Track:
        track = Track(id=uuid.uuid4().hex[:8], name=name, kind=kind)
        self.tracks.append(track)
        return track

    def copy_into_audio(self, source: Path) -> Path:
        target = Path(self.root) / "audio" / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return target

