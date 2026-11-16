# Music Master

Primer prototipo local de un asistente musical orientado a tarareos, MIDI y VST3.

## Qué incluye esta versión

- Proyecto multicanal con pistas de guía de audio y pistas MIDI.
- Grabación de una guía desde el micrófono cuando `sounddevice` está instalado.
- Importación de WAV/MP3 como guía (el MP3 se conserva como referencia; para editar se recomienda WAV/FLAC).
- Selector del instrumento que estás tarareando (voz, bajo, guitarra, piano, violín, flauta o saxofón) para filtrar mejor el rango de notas.
- Conversión offline de una guía a una nueva pista MIDI mediante Basic Pitch.
- Edición MIDI básica: transposición, cuantización y cambio de tempo.
- Prompts locales para acciones concretas, por ejemplo:
  - `transportá la melodía 3 semitonos`
  - `subí la melodía una tercera menor`
  - `cuantizá a corcheas`
  - `cambiá el tempo a 96`
- Exportación de MIDI y mezcla de audio guía a WAV.
- Preparado para agregar Basic Pitch y Pedalboard como módulos opcionales.

## Ejecutar

Requiere Python 3.11+ en Windows.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m music_master
```

La aplicación también puede abrirse sin instalar dependencias, usando solamente la biblioteca estándar de Python:

```powershell
python -m music_master
```

## Dependencias opcionales

- `sounddevice` y `soundfile`: grabación desde micrófono y exportación WAV.
- `mido` y `python-rtmidi`: entrada MIDI.
- `basic-pitch`: conversión de un tarareo a MIDI.
- `pedalboard`: carga/render de plugins VST3.

Los archivos de audio originales y los renders se guardan dentro de cada proyecto. El MIDI es la representación editable principal; las guías de audio son referencias no destructivas.

