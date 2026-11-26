# Video Finder

[English](#english) · [Italiano](#italiano)

## English

Windows desktop app to search for videos by title across 1,300+ sites supported by yt-dlp, preview them inside the app, and download video, audio, or both at the quality you choose.

### Download

The portable executable is in [Releases](../../releases/latest): `VideoFinder.exe`, no installation required. ffmpeg and the mpv player are bundled.

### Features

- Cross-platform search: YouTube, Dailymotion and web results filtered to sites supported by yt-dlp (1,356 domains).
- Site suggestions while typing in the platform field.
- Built-in mpv preview with play/pause and a seek bar.
- Download video + audio, video only, or MP3 audio only.
- Video quality from 240p to 2160p; MP3 audio from 96 to 320 kbps.
- Custom download folder.

### Requirements

- Windows 10/11 64-bit.
- Internet connection.

### Notes

- Sites that require an account (Vimeo, Instagram, Facebook, ...) may refuse downloads: the app shows the yt-dlp error.
- Search on non-native sites uses a web engine (DuckDuckGo/Google). If it is rate-limited, try again.
- Preview is capped at 720p; downloads use the selected quality.

### Development

Requirements: Python 3.13+, ffmpeg in PATH, `libmpv-2.dll` in the `vendor/` folder.

```bash
pip install -r requirements.txt
python video_finder.py
```

Build the Windows executable:

```bash
pyinstaller --noconfirm --onefile --windowed --name VideoFinder ^
  --icon ThaSkull.ico --add-data "ThaSkull.ico;." ^
  --collect-all yt_dlp --collect-all ttkbootstrap --collect-all curl_cffi ^
  --collect-all ddgs --collect-all primp --hidden-import mpv ^
  --add-binary "C:\path\to\ffmpeg.exe;." ^
  --add-binary "vendor\libmpv-2.dll;." video_finder.py
```

---

## Italiano

App desktop Windows per cercare un video per titolo, riprodurlo in un player integrato e scaricare video, audio o entrambi scegliendo la qualità.

### Download

L'eseguibile portable è nella sezione [Releases](../../releases/latest): `VideoFinder.exe`, nessuna installazione richiesta. Include ffmpeg e il player mpv.

### Funzioni

- Ricerca multipiattaforma: YouTube, Dailymotion e ricerca web filtrata sui siti supportati da yt-dlp (1356 domini).
- Suggerimenti dei siti mentre scrivi nel campo "Piattaforma".
- Anteprima video dentro l'app con player mpv: play/pausa, barra di avanzamento e tempo.
- Download: video + audio, solo video, solo audio MP3.
- Qualità video da 240p a 2160p; qualità audio MP3 da 96 a 320 kbps.
- Cartella di destinazione personalizzabile.

### Requisiti

- Windows 10/11 a 64 bit.
- Connessione internet.

### Note

- I siti che richiedono un account (Vimeo, Instagram, Facebook, ...) possono rifiutare il download: l'app mostra l'errore di yt-dlp.
- La ricerca sui siti non nativi usa un motore web (DuckDuckGo/Google). Se il motore limita le richieste, riprova.
- L'anteprima arriva fino a 720p; il download usa la qualità scelta.

### Sviluppo

Requisiti: Python 3.13+, ffmpeg nel PATH, `libmpv-2.dll` nella cartella `vendor/`.

```bash
pip install -r requirements.txt
python video_finder.py
```

Build dell'eseguibile Windows:

```bash
pyinstaller --noconfirm --onefile --windowed --name VideoFinder ^
  --icon ThaSkull.ico --add-data "ThaSkull.ico;." ^
  --collect-all yt_dlp --collect-all ttkbootstrap --collect-all curl_cffi ^
  --collect-all ddgs --collect-all primp --hidden-import mpv ^
  --add-binary "C:\percorso\ffmpeg.exe;." ^
  --add-binary "vendor\libmpv-2.dll;." video_finder.py
```
