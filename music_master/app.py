from __future__ import annotations

import threading
import uuid
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .audio import play_audio, play_audio_segment, record_until_stopped, synthesize_midi_tracks, transcribe_to_midi, trim_audio
from .midi import parse_action, quantize, read_midi_notes, transpose, write_midi
from .models import MidiFragment, MidiNote, Project


INPUT_INSTRUMENTS = {
    "Voz / tarareo": (80, 1200),
    "Bajo": (30, 350),
    "Guitarra": (70, 1400),
    "Guitarra eléctrica": (60, 1400),
    "Piano": (27, 4200),
    "Violín": (190, 3500),
    "Flauta": (250, 2500),
    "Saxofón": (120, 1200),
}

INPUT_SOURCES = {
    "Tarareo / voz": "Voz / tarareo",
    "Guitarra eléctrica por línea": "Guitarra eléctrica",
}


class MusicMasterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Music Master — prototipo local")
        self.geometry("920x620")
        self.project: Project | None = None
        self.track_ids: dict[str, object] = {}
        self.input_instrument = tk.StringVar(value="Voz / tarareo")
        self.track_instrument = tk.StringVar(value="Voz / tarareo")
        self.playback_stop = threading.Event()
        self.playback_thread: threading.Thread | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Nuevo", command=self.new_project).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Abrir", command=self.open_project).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Guardar", command=self.save_project).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Importar guía", command=self.import_guide).pack(side="left", padx=12)
        ttk.Button(toolbar, text="Grabar tarareo", command=self.record_guide).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Tarareo → MIDI", command=self.transcribe_selected_guide).pack(side="left", padx=3)
        ttk.Label(toolbar, text="Instrumento:").pack(side="left", padx=(16, 3))
        instrument_box = ttk.Combobox(toolbar, textvariable=self.input_instrument, values=list(INPUT_INSTRUMENTS), state="readonly", width=18)
        instrument_box.pack(side="left", padx=3)
        ttk.Button(toolbar, text="Nueva pista MIDI", command=self.add_midi_track).pack(side="left", padx=12)
        ttk.Button(toolbar, text="Exportar MIDI", command=self.export_midi).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Reproducir seleccionado", command=self.play_selected).pack(side="left", padx=(12, 3))
        ttk.Button(toolbar, text="Reproducir MIDI", command=self.play_all_midi).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Detener", command=self.stop_playback).pack(side="left", padx=3)

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(body, padding=8)
        right = ttk.Frame(body, padding=8)
        body.add(left, weight=1)
        body.add(right, weight=2)

        ttk.Label(left, text="Pistas", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.track_list = tk.Listbox(left, exportselection=False)
        self.track_list.pack(fill="both", expand=True, pady=8)
        self.track_list.bind("<<ListboxSelect>>", self._select_track)
        ttk.Button(left, text="Eliminar pista / tarareo", command=self.remove_track).pack(fill="x")
        ttk.Button(left, text="Silenciar / activar", command=self.toggle_mute).pack(fill="x", pady=(4, 0))

        ttk.Label(right, text="Asistente musical", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.info = tk.Text(right, height=5, wrap="word", state="disabled", background="#f4f4f4")
        self.info.pack(fill="x", pady=4)
        instrument_row = ttk.Frame(right)
        instrument_row.pack(fill="x", pady=(0, 6))
        ttk.Label(instrument_row, text="Instrumento de la pista:").pack(side="left")
        ttk.Combobox(instrument_row, textvariable=self.track_instrument, values=list(INPUT_INSTRUMENTS), state="readonly", width=18).pack(side="left", padx=6)
        ttk.Button(instrument_row, text="Asignar", command=self.assign_track_instrument).pack(side="left")
        ttk.Label(right, text="Arreglo — arrastrá los bloques MIDI para moverlos:").pack(anchor="w")
        arrangement_scroll = ttk.Scrollbar(right, orient="horizontal")
        self.arrangement_canvas = tk.Canvas(right, height=330, background="#25282d", highlightthickness=0, xscrollcommand=arrangement_scroll.set)
        arrangement_scroll.configure(command=self.arrangement_canvas.xview)
        self.arrangement_canvas.pack(fill="both", expand=True, pady=(2, 6))
        arrangement_scroll.pack(fill="x")
        self.arrangement_canvas.bind("<ButtonPress-1>", self.arrangement_press)
        self.arrangement_canvas.bind("<B1-Motion>", self.arrangement_motion)
        self.arrangement_canvas.bind("<ButtonRelease-1>", self.arrangement_release)
        ttk.Label(right, text="Fragmentos MIDI — arrastrá los bloques para moverlos:").pack(anchor="w")
        self.fragment_canvas = tk.Canvas(right, height=110, background="#20252b", highlightthickness=0)
        self.fragment_canvas.pack(fill="x", pady=(2, 6))
        self.fragment_canvas.bind("<ButtonPress-1>", self.fragment_press)
        self.fragment_canvas.bind("<B1-Motion>", self.fragment_motion)
        self.fragment_canvas.bind("<ButtonRelease-1>", self.fragment_release)
        fragment_buttons = ttk.Frame(right)
        fragment_buttons.pack(fill="x")
        ttk.Button(fragment_buttons, text="Renombrar fragmento", command=self.rename_fragment).pack(side="left")
        self.info_message("Creá un proyecto para comenzar.\n\nLas guías de audio son referencias; las pistas MIDI son editables y luego pueden conectarse a VST3.")
        prompt_row = ttk.Frame(right)
        prompt_row.pack(fill="x")
        self.prompt = ttk.Entry(prompt_row)
        self.prompt.pack(side="left", fill="x", expand=True)
        self.prompt.bind("<Return>", lambda _event: self.apply_prompt())
        ttk.Button(prompt_row, text="Aplicar prompt", command=self.apply_prompt).pack(side="left", padx=(8, 0))

        self.status = tk.StringVar(value="Listo")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def new_project(self) -> None:
        folder = filedialog.askdirectory(title="Elegí la carpeta del proyecto")
        if not folder:
            return
        self.project = Project.create(Path(folder), Path(folder).name)
        self.project.add_track("Tarareo guía", "guide")
        self.project.save()
        self.refresh()
        self.status.set("Proyecto creado")

    def open_project(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Music Master", "project.json")])
        if path:
            self.project = Project.load(Path(path))
            self.refresh()
            self.status.set("Proyecto abierto")

    def save_project(self) -> None:
        if self.project:
            self.project.save()
            self.status.set("Proyecto guardado")

    def import_guide(self) -> None:
        if not self.project:
            messagebox.showinfo("Proyecto", "Creá o abrí un proyecto primero")
            return
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.wav *.mp3 *.flac"), ("Todos", "*.*")])
        if not path:
            return
        source = Path(path)
        target = self.project.copy_into_audio(source)
        track = self.project.add_track(source.stem, "guide")
        track.instrument = self.input_instrument.get()
        track.source = str(target.relative_to(self.project.root))
        self.project.save()
        self.refresh()
        self.status.set(f"Guía importada: {source.name}")

    def record_guide(self) -> None:
        self.open_recording_modal()
        return
        if not self.project:
            messagebox.showinfo("Proyecto", "Creá o abrí un proyecto primero")
            return
        seconds = simpledialog.askfloat("Grabar tarareo", "Duración en segundos:", initialvalue=10, minvalue=1, maxvalue=120)
        if not seconds:
            return
        target = Path(self.project.root) / "audio" / f"tarareo_{len(self.project.tracks)+1:02d}.wav"
        self.status.set("Grabando…")
        def work() -> None:
            try:
                record_wav(target, seconds)
                track = self.project.add_track(target.stem, "guide")
                track.instrument = self.input_instrument.get()
                track.source = str(target.relative_to(self.project.root))
                self.project.save()
                self.after(0, lambda: (self.refresh(), self.status.set("Grabación lista")))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Grabación", str(exc)))
                self.after(0, lambda: self.status.set("Error de grabación"))
        threading.Thread(target=work, daemon=True).start()

    def open_recording_modal(self) -> None:
        if not self.project:
            messagebox.showinfo("Proyecto", "Creá o abrí un proyecto primero")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Grabadora de tarareo")
        dialog.geometry("760x520")
        dialog.transient(self)
        dialog.grab_set()
        audio_dir = Path(self.project.root) / "audio"
        preview = audio_dir / "_grabacion_preview.wav"
        stop_event = threading.Event()
        state = {"recording": False}
        start = tk.StringVar(value="0")
        end = tk.StringVar(value="0")
        instrument = tk.StringVar(value=self.input_instrument.get())
        source_type = tk.StringVar(value="Tarareo / voz")
        fragment_name = tk.StringVar(value=f"Fragmento {len(self.project.tracks) + 1}")
        ttk.Label(dialog, text="Grabá, escuchá, recortá y convertí el fragmento a MIDI.", wraplength=430).pack(pady=12)
        controls = ttk.Frame(dialog)
        controls.pack(pady=4)
        status = ttk.Label(dialog, text="Listo")
        status.pack(pady=4)
        waveform = tk.Canvas(dialog, height=190, background="#20252b", highlightthickness=0)
        waveform.pack(fill="x", padx=16, pady=(4, 10))
        waveform_state = {"duration": 0.0, "handle": None}

        def x_to_seconds(x: float) -> float:
            width = max(1, waveform.winfo_width())
            return max(0.0, min(waveform_state["duration"], (x / width) * waveform_state["duration"]))

        def seconds_to_x(seconds: float) -> float:
            width = max(1, waveform.winfo_width())
            duration = waveform_state["duration"] or 1.0
            return max(0.0, min(width, seconds / duration * width))

        def draw_waveform() -> None:
            waveform.delete("all")
            duration = waveform_state["duration"]
            if not preview.exists() or duration <= 0:
                waveform.create_text(12, 20, anchor="w", fill="#c7cbd1", text="La forma de onda aparecerá después de grabar")
                return
            try:
                import numpy as np
                import soundfile as sf
                data, _rate = sf.read(str(preview), dtype="float32", always_2d=True)
                mono = data.mean(axis=1)
                width = max(1, waveform.winfo_width())
                chunk = max(1, len(mono) // width)
                peaks = [float(np.max(np.abs(mono[i:i + chunk]))) for i in range(0, len(mono), chunk)][:width]
                for x, peak in enumerate(peaks):
                    height = max(1, peak * 80)
                    waveform.create_line(x, 95 - height, x, 95 + height, fill="#65b5d8")
            except Exception:
                pass
            start_x = seconds_to_x(float(start.get() or 0))
            end_x = seconds_to_x(float(end.get() or duration))
            waveform.create_rectangle(start_x, 0, end_x, 190, fill="#5b86a6", stipple="gray25", outline="")
            waveform.create_line(start_x, 0, start_x, 190, fill="#58d68d", width=3)
            waveform.create_line(end_x, 0, end_x, 190, fill="#ffb347", width=3)
            waveform.create_text(start_x + 5, 12, anchor="nw", fill="#58d68d", text="INICIO")
            waveform.create_text(end_x - 5, 12, anchor="ne", fill="#ffb347", text="FINAL")

        def waveform_press(event) -> None:
            start_x = seconds_to_x(float(start.get() or 0))
            end_x = seconds_to_x(float(end.get() or waveform_state["duration"]))
            if abs(event.x - start_x) <= 12:
                waveform_state["handle"] = "start"
            elif abs(event.x - end_x) <= 12:
                waveform_state["handle"] = "end"
            else:
                waveform_state["handle"] = "start" if event.x < (start_x + end_x) / 2 else "end"
            waveform_motion(event)

        def waveform_motion(event) -> None:
            handle = waveform_state["handle"]
            if not handle:
                return
            value = x_to_seconds(event.x)
            if handle == "start":
                value = min(value, float(end.get() or waveform_state["duration"]) - 0.01)
                start.set(f"{max(0.0, value):.2f}")
            else:
                value = max(value, float(start.get() or 0) + 0.01)
                duration = waveform_state["duration"]
                end.set(f"{min(duration, value):.2f}")
            draw_waveform()

        def waveform_release(_event) -> None:
            waveform_state["handle"] = None

        waveform.bind("<ButtonPress-1>", waveform_press)
        waveform.bind("<B1-Motion>", waveform_motion)
        waveform.bind("<ButtonRelease-1>", waveform_release)

        def update_duration() -> None:
            try:
                import soundfile as sf
                seconds = sf.info(str(preview)).duration
            except Exception:
                seconds = 0
            end.set(f"{seconds:.2f}")
            waveform_state["duration"] = seconds
            draw_waveform()
            status.configure(text=f"Grabación: {seconds:.2f} segundos")

        def start_recording() -> None:
            if state["recording"]:
                return
            state["recording"] = True
            stop_event.clear()
            status.configure(text="Grabando... pulsá Detener cuando termines")
            def work() -> None:
                try:
                    record_until_stopped(preview, stop_event)
                    self.after(0, update_duration)
                except Exception as exc:
                    self.after(0, lambda: messagebox.showerror("Grabación", str(exc), parent=dialog))
                finally:
                    state["recording"] = False
                    self.after(0, lambda: status.configure(text="Grabación lista"))
            threading.Thread(target=work, daemon=True).start()

        def stop_recording() -> None:
            stop_event.set()

        def listen() -> None:
            if preview.exists():
                self.start_playback(lambda: play_audio_segment(preview, float(start.get() or 0), float(end.get() or waveform_state["duration"])), "Reproduciendo selección...")
                return

        def source_changed(_event=None) -> None:
            instrument.set(INPUT_SOURCES[source_type.get()])
            if False:
                self.start_playback(lambda: play_audio(preview), "Reproduciendo grabación...")

        def convert() -> None:
            if state["recording"] or not preview.exists():
                messagebox.showinfo("Grabación", "Primero grabá y detené el fragmento.", parent=dialog)
                return
            try:
                start_value = float(start.get())
                end_value = float(end.get())
                if end_value <= start_value:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Recorte", "Indicá un inicio y un final válidos.", parent=dialog)
                return
            name = fragment_name.get().strip() or "Fragmento sin nombre"
            final_audio = audio_dir / f"{name.replace(' ', '_')}_{uuid.uuid4().hex[:6]}.wav"
            try:
                trim_audio(preview, final_audio, start_value, end_value)
            except Exception as exc:
                messagebox.showerror("Recorte", str(exc), parent=dialog)
                return
            status.configure(text="Convirtiendo a MIDI... puede tardar")
            selected_instrument = INPUT_SOURCES[source_type.get()]
            minimum, maximum = INPUT_INSTRUMENTS[selected_instrument]
            def work() -> None:
                try:
                    midi_path = transcribe_to_midi(final_audio, Path(self.project.root) / "midi", self.project.tempo, minimum, maximum)
                    notes = read_midi_notes(midi_path)
                    self.after(0, lambda: self.add_fragment_result(final_audio, notes, selected_instrument, name, dialog))
                except Exception as exc:
                    self.after(0, lambda: messagebox.showerror("Conversión a MIDI", str(exc), parent=dialog))
                    self.after(0, lambda: status.configure(text="Error al convertir"))
            threading.Thread(target=work, daemon=True).start()

        ttk.Button(controls, text="Grabar", command=start_recording).grid(row=0, column=0, padx=4)
        ttk.Button(controls, text="Detener", command=stop_recording).grid(row=0, column=1, padx=4)
        ttk.Button(controls, text="Escuchar", command=listen).grid(row=0, column=2, padx=4)
        fields = ttk.Frame(dialog)
        fields.pack(fill="x", padx=18, pady=8)
        ttk.Label(fields, text="Inicio (s):").grid(row=0, column=0, sticky="w")
        ttk.Entry(fields, textvariable=start, width=10).grid(row=0, column=1, padx=5)
        ttk.Label(fields, text="Final (s):").grid(row=0, column=2, sticky="w")
        ttk.Entry(fields, textvariable=end, width=10).grid(row=0, column=3, padx=5)
        ttk.Button(fields, text="Actualizar onda", command=draw_waveform).grid(row=0, column=4, padx=8)
        ttk.Label(fields, text="Entrada:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        source_box = ttk.Combobox(fields, textvariable=source_type, values=list(INPUT_SOURCES), state="readonly", width=28)
        source_box.grid(row=1, column=1, columnspan=3, sticky="w", pady=(8, 0))
        source_box.bind("<<ComboboxSelected>>", source_changed)
        ttk.Label(fields, text="Instrumento detectado:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(fields, textvariable=instrument).grid(row=2, column=1, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(fields, text="Nombre del fragmento:").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(fields, textvariable=fragment_name, width=28).grid(row=3, column=1, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(dialog, text="Convertir a MIDI y agregar a la pista", command=convert).pack(pady=10)
        dialog.protocol("WM_DELETE_WINDOW", lambda: (stop_event.set(), dialog.destroy()))

    def add_fragment_result(self, audio_path: Path, notes: list[MidiNote], instrument: str, name: str, dialog: tk.Toplevel) -> None:
        if not self.project:
            return
        track = next((item for item in self.project.tracks if item.kind == "midi" and item.instrument == instrument), None)
        if track is None:
            track = self.project.add_track(instrument, "midi")
            track.instrument = instrument
        if not track.fragments and track.notes:
            track.fragments = [MidiFragment(uuid.uuid4().hex[:8], "Fragmento original", 0.0, track.notes)]
        offset = max((note.start + note.duration for note in track.notes), default=0.0)
        fragment_notes = [MidiNote(note.pitch, note.start + offset, note.duration, note.velocity, note.channel) for note in notes]
        fragment = MidiFragment(uuid.uuid4().hex[:8], name, offset, fragment_notes)
        track.fragments.append(fragment)
        track.notes.extend(fragment_notes)
        guide = self.project.add_track(f"Guía - {name}", "guide")
        guide.instrument = instrument
        guide.source = str(audio_path.relative_to(self.project.root))
        guide.muted = True
        self.project.save()
        self.refresh()
        for index, item in enumerate(self.project.tracks):
            if item.id == track.id:
                self.track_list.selection_set(index)
                self.track_list.see(index)
                break
        dialog.destroy()
        self.status.set(f"Fragmento '{name}' agregado a {track.name}")
        self.info_message(f"Fragmento MIDI agregado: {name}\nPista: {track.name}\nInstrumento: {instrument}\nNotas: {len(notes)}")

    def add_midi_track(self) -> None:
        if not self.project:
            messagebox.showinfo("Proyecto", "Creá o abrí un proyecto primero")
            return
        name = simpledialog.askstring("Nueva pista MIDI", "Nombre:", initialvalue="Melodía MIDI")
        if name:
            track = self.project.add_track(name, "midi")
            self.project.save()
            self.refresh()
            self.track_list.selection_set(len(self.project.tracks) - 1)
            self.status.set(f"Pista MIDI creada: {name}")

    def transcribe_selected_guide(self) -> None:
        if not self.project or not self.track_list.curselection():
            messagebox.showinfo("Tarareo", "Seleccioná una pista guía de audio")
            return
        guide = self.project.tracks[self.track_list.curselection()[0]]
        if guide.kind != "guide" or not guide.source:
            messagebox.showinfo("Tarareo", "La pista seleccionada no tiene un audio guía")
            return
        audio_path = Path(self.project.root) / guide.source
        if not audio_path.exists():
            messagebox.showerror("Tarareo", f"No existe el archivo:\n{audio_path}")
            return
        self.status.set("Analizando tarareo… puede tardar unos segundos")
        def work() -> None:
            try:
                instrument = guide.instrument or self.input_instrument.get()
                minimum_frequency, maximum_frequency = INPUT_INSTRUMENTS.get(instrument, (None, None))
                midi_path = transcribe_to_midi(
                    audio_path,
                    Path(self.project.root) / "midi",
                    self.project.tempo,
                    minimum_frequency,
                    maximum_frequency,
                )
                notes = read_midi_notes(midi_path)
                selected = self.project.tracks[self.track_list.curselection()[0]]
                if selected.kind == "midi":
                    track = selected
                    track.name = f"{track.name} (desde {guide.name})"
                else:
                    track = self.project.add_track(f"{guide.name} MIDI", "midi")
                track.source = str(midi_path.relative_to(self.project.root))
                track.notes = notes
                track.instrument = instrument
                self.project.save()
                self.after(0, lambda: (self.refresh(), self.status.set(f"MIDI generado: {len(notes)} notas")))
                self.after(0, lambda: self.info_message(f"Tarareo convertido a MIDI.\nInstrumento: {instrument}\nNotas detectadas: {len(notes)}\nArchivo: {midi_path.name}\n\nAhora podés seleccionar la pista MIDI y aplicar prompts."))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Conversión a MIDI", str(exc)))
                self.after(0, lambda: self.status.set("Error al convertir el tarareo"))
        threading.Thread(target=work, daemon=True).start()

    def remove_track(self) -> None:
        if not self.project or not self.track_list.curselection():
            return
        index = self.track_list.curselection()[0]
        track = self.project.tracks[index]
        if not messagebox.askyesno("Eliminar", f"¿Eliminar '{track.name}' del proyecto?\nSi es una guía, también se borrará su archivo de audio."):
            return
        if track.kind == "guide" and track.source:
            source = Path(self.project.root) / track.source
            if source.exists():
                source.unlink()
        self.project.tracks.pop(index)
        self.project.save()
        self.refresh()

    def selected_track(self):
        if not self.project or not self.track_list.curselection():
            return None
        return self.project.tracks[self.track_list.curselection()[0]]

    def _sync_track_notes(self, track) -> None:
        if track.fragments:
            track.notes = [note for fragment in track.fragments for note in fragment.notes]

    def draw_arrangement(self) -> None:
        canvas = self.arrangement_canvas
        canvas.delete("all")
        if not self.project:
            canvas.create_text(12, 25, anchor="w", fill="#c7cbd1", text="Creá o abrí un proyecto para comenzar")
            return
        scale = 70.0
        ruler = 28
        lane_height = 68
        max_beats = max((note.start + note.duration for track in self.project.tracks for note in track.notes), default=16.0)
        width = max(canvas.winfo_width(), int((max_beats + 4) * scale))
        height = ruler + max(1, len(self.project.tracks)) * lane_height
        canvas.configure(scrollregion=(0, 0, width, height))
        canvas.create_rectangle(0, 0, width, ruler, fill="#30343a", outline="")
        for beat in range(int(max_beats) + 5):
            x = beat * scale
            major = beat % 4 == 0
            canvas.create_line(x, 0, x, height, fill="#60656c" if major else "#3b4046", dash=() if major else (2, 4))
            if major:
                canvas.create_text(x + 4, 8, anchor="nw", fill="#d6d9dd", text=f"{beat // 4 + 1}.1")
        for row, track in enumerate(self.project.tracks):
            y1 = ruler + row * lane_height
            y2 = y1 + lane_height
            canvas.create_rectangle(0, y1, width, y2, fill="#292d32" if row % 2 else "#25282d", outline="#3b4046")
            canvas.create_text(8, y1 + 8, anchor="nw", fill="#d6d9dd", text=f"{row + 1}. {track.name}")
            if track.kind == "midi":
                for fragment in track.fragments:
                    duration = max(0.5, fragment.duration)
                    x1 = fragment.start * scale
                    x2 = x1 + duration * scale
                    color = "#39739d" if not track.muted else "#555b61"
                    tag = f"arr:{track.id}:{fragment.id}"
                    canvas.create_rectangle(x1, y1 + 25, x2, y2 - 7, fill=color, outline="#8ac4e8", tags=(tag,))
                    canvas.create_text(x1 + 5, y1 + 31, anchor="nw", fill="white", text=fragment.name, tags=(tag,))
            elif track.kind == "guide":
                canvas.create_text(8, y1 + 42, anchor="w", fill="#8f989f", text="guía de audio")

    def arrangement_press(self, event) -> None:
        canvas = self.arrangement_canvas
        hits = canvas.find_overlapping(event.x, event.y, event.x, event.y)
        self.arrangement_drag = None
        for item in reversed(hits):
            for tag in canvas.gettags(item):
                if tag.startswith("arr:"):
                    _, track_id, fragment_id = tag.split(":", 2)
                    track = next((t for t in self.project.tracks if t.id == track_id), None)
                    fragment = next((f for f in track.fragments if f.id == fragment_id), None) if track else None
                    if track and fragment:
                        self.arrangement_drag = (track, fragment)
                        self.arrangement_last_x = event.x
                        index = self.project.tracks.index(track)
                        self.track_list.selection_clear(0, "end")
                        self.track_list.selection_set(index)
                        self.track_list.see(index)
                        self._select_track()
                        return
        row = int((event.y - 28) // 68)
        if 0 <= row < len(self.project.tracks):
            self.track_list.selection_clear(0, "end")
            self.track_list.selection_set(row)
            self._select_track()

    def arrangement_motion(self, event) -> None:
        if not getattr(self, "arrangement_drag", None):
            return
        track, fragment = self.arrangement_drag
        delta = (event.x - self.arrangement_last_x) / 70.0
        if abs(delta) < 0.01:
            return
        new_start = max(0.0, fragment.start + delta)
        actual_delta = new_start - fragment.start
        fragment.start = new_start
        for note in fragment.notes:
            note.start += actual_delta
        self.arrangement_last_x = event.x
        self._sync_track_notes(track)
        self.draw_arrangement()
        self.draw_fragment_timeline()

    def arrangement_release(self, _event) -> None:
        if getattr(self, "arrangement_drag", None) and self.project:
            self.project.save()
            self.status.set(f"Fragmento movido: {self.arrangement_drag[1].name}")
        self.arrangement_drag = None

    def draw_fragment_timeline(self) -> None:
        self.fragment_canvas.delete("all")
        track = self.selected_track()
        if not track or track.kind != "midi":
            self.fragment_canvas.create_text(10, 20, anchor="w", fill="#c7cbd1", text="Seleccioná una pista MIDI")
            return
        fragments = track.fragments
        if not fragments:
            self.fragment_canvas.create_text(10, 20, anchor="w", fill="#c7cbd1", text="Todavía no hay fragmentos")
            return
        scale = 70.0
        for fragment in fragments:
            width = max(70.0, fragment.duration * scale)
            x1 = fragment.start * scale
            x2 = x1 + width
            self.fragment_canvas.create_rectangle(x1, 20, x2, 75, fill="#4479a8", outline="#b7d7f5", tags=(f"fragment:{fragment.id}",))
            self.fragment_canvas.create_text(x1 + 5, 47, anchor="w", fill="white", text=fragment.name, tags=(f"fragment:{fragment.id}",))

    def fragment_press(self, event) -> None:
        hits = self.fragment_canvas.find_overlapping(event.x, event.y, event.x, event.y)
        self.drag_fragment = None
        track = self.selected_track()
        if not track:
            return
        for item in hits:
            tags = self.fragment_canvas.gettags(item)
            for tag in tags:
                if tag.startswith("fragment:"):
                    fragment_id = tag.split(":", 1)[1]
                    self.drag_fragment = next((f for f in track.fragments if f.id == fragment_id), None)
                    self.selected_fragment = self.drag_fragment
                    self.drag_x = event.x
                    return

    def fragment_motion(self, event) -> None:
        if not getattr(self, "drag_fragment", None):
            return
        delta = (event.x - self.drag_x) / 70.0
        if abs(delta) < 0.01:
            return
        fragment = self.drag_fragment
        new_start = max(0.0, fragment.start + delta)
        actual_delta = new_start - fragment.start
        fragment.start = new_start
        for note in fragment.notes:
            note.start += actual_delta
        self.drag_x = event.x
        self._sync_track_notes(self.selected_track())
        self.draw_fragment_timeline()

    def fragment_release(self, _event) -> None:
        if getattr(self, "drag_fragment", None) and self.project:
            self.project.save()
            self.status.set(f"Fragmento movido: {self.drag_fragment.name}")
        self.drag_fragment = None

    def rename_fragment(self) -> None:
        fragment = getattr(self, "selected_fragment", None)
        track = self.selected_track()
        if not track or track.kind != "midi" or not track.fragments:
            return
        if fragment is None:
            fragment = track.fragments[0]
        name = simpledialog.askstring("Fragmento MIDI", "Nombre:", initialvalue=fragment.name, parent=self)
        if name:
            fragment.name = name.strip()
            self.project.save()
            self.draw_fragment_timeline()
            self.status.set(f"Fragmento renombrado: {fragment.name}")

    def toggle_mute(self) -> None:
        track = self.selected_track()
        if not track:
            return
        track.muted = not track.muted
        self.project.save()
        self.refresh()
        self.status.set(f"{'Silenciada' if track.muted else 'Activada'}: {track.name}")

    def assign_track_instrument(self) -> None:
        track = self.selected_track()
        if not track:
            return
        track.instrument = self.track_instrument.get()
        self.project.save()
        self.refresh()
        self.status.set(f"Instrumento asignado: {track.instrument}")

    def stop_playback(self) -> None:
        self.playback_stop.set()
        try:
            import sounddevice as sd
            sd.stop()
        except ImportError:
            pass
        self.status.set("Reproducción detenida")

    def start_playback(self, work, label: str) -> None:
        self.stop_playback()
        self.playback_stop.clear()
        self.status.set(label)

        def runner() -> None:
            try:
                work()
                if not self.playback_stop.is_set():
                    self.after(0, lambda: self.status.set("Reproducción terminada"))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Reproducción", str(exc)))
                self.after(0, lambda: self.status.set("Error de reproducción"))

        self.playback_thread = threading.Thread(target=runner, daemon=True)
        self.playback_thread.start()

    def play_selected(self) -> None:
        track = self.selected_track()
        if not track:
            messagebox.showinfo("Reproducción", "Seleccioná una pista")
            return
        if track.muted:
            messagebox.showinfo("Reproducción", "La pista está silenciada")
            return
        if track.kind == "guide" and track.source:
            path = Path(self.project.root) / track.source
            self.start_playback(lambda: play_audio(path), "Reproduciendo guía...")
        elif track.kind == "midi":
            self.start_playback(lambda: self._play_midi([track]), "Reproduciendo pista MIDI...")

    def play_all_midi(self) -> None:
        if not self.project:
            return
        tracks = [track for track in self.project.tracks if track.kind == "midi" and not track.muted]
        self.start_playback(lambda: self._play_midi(tracks), "Reproduciendo todas las pistas MIDI...")

    def _play_midi(self, tracks) -> None:
        import sounddevice as sd
        audio, rate = synthesize_midi_tracks(tracks, self.project.tempo)
        sd.play(audio, rate)
        sd.wait()

    def _select_track(self, _event=None) -> None:
        if not self.project or not self.track_list.curselection():
            return
        track = self.project.tracks[self.track_list.curselection()[0]]
        self.track_instrument.set(track.instrument or "Voz / tarareo")
        details = f"Nombre: {track.name}\nTipo: {track.kind}\nInstrumento VST: {track.instrument or 'sin asignar'}\n"
        details += f"Fuente: {track.source or 'ninguna'}\nNotas MIDI: {len(track.notes)}"
        self.info_message(details)
        self.draw_arrangement()
        self.draw_fragment_timeline()

    def apply_prompt(self) -> None:
        if not self.project or not self.track_list.curselection():
            messagebox.showinfo("Pista", "Seleccioná una pista MIDI")
            return
        track = self.project.tracks[self.track_list.curselection()[0]]
        if track.kind != "midi":
            messagebox.showinfo("Pista", "El prompt se aplica inicialmente a pistas MIDI")
            return
        action = parse_action(self.prompt.get())
        if not action:
            self.info_message("Todavía no reconozco ese comando en el modo local.\n\nProbá: 'transportá 3 semitonos', 'subí una tercera menor', 'cuantizá a corcheas' o 'cambiá el tempo a 96'.")
            return
        command, value = action
        if command == "duplicate_fragment":
            target_name = str(value).casefold()
            fragment = next((item for item in track.fragments if item.name.casefold() == target_name), None)
            if fragment is None:
                self.info_message(f"No encontré el fragmento '{value}' en la pista {track.name}.")
                return
            offset = max((note.start + note.duration for note in track.notes), default=0.0)
            delta = offset - fragment.start
            copied_notes = [MidiNote(note.pitch, note.start + delta, note.duration, note.velocity, note.channel) for note in fragment.notes]
            copy = MidiFragment(uuid.uuid4().hex[:8], f"{fragment.name} copia", offset, copied_notes)
            track.fragments.append(copy)
            track.notes.extend(copied_notes)
            result = f"Fragmento duplicado: {fragment.name} → {copy.name}."
        elif command == "transpose":
            transpose(track, int(value))
            result = f"Pista transportada {value} semitonos."
        elif command == "quantize":
            quantize(track, float(value))
            result = "Pista cuantizada."
        else:
            self.project.tempo = int(value)
            result = f"Tempo del proyecto cambiado a {value} BPM."
        self.project.save()
        self.info_message(result + "\n\nLa guía original no fue modificada.")
        self.status.set(result)

    def export_midi(self) -> None:
        if not self.project or not self.track_list.curselection():
            return
        track = self.project.tracks[self.track_list.curselection()[0]]
        if track.kind != "midi":
            messagebox.showinfo("Exportar MIDI", "Seleccioná una pista MIDI")
            return
        path = filedialog.asksaveasfilename(initialdir=str(Path(self.project.root) / "midi"), defaultextension=".mid", filetypes=[("MIDI", "*.mid")])
        if path:
            write_midi(track, Path(path), self.project.tempo)
            self.status.set(f"MIDI exportado: {Path(path).name}")

    def refresh(self) -> None:
        self.track_list.delete(0, "end")
        if self.project:
            for track in self.project.tracks:
                state = " (silenciada)" if track.muted else ""
                self.track_list.insert("end", f"[{track.kind.upper()}] {track.name}{state}")
        self.draw_arrangement()
        self.draw_fragment_timeline()

    def info_message(self, message: str) -> None:
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", message)
        self.info.configure(state="disabled")


def main() -> None:
    app = MusicMasterApp()
    app.mainloop()

