# Video Finder

App desktop Windows per cercare un video per titolo, riprodurlo in un player integrato e scaricare video, audio o entrambi scegliendo la qualità.

## Download

L'eseguibile portable è nella sezione [Releases](../../releases/latest): `VideoFinder.exe`, nessuna installazione richiesta. Include ffmpeg e il player mpv.

## Funzioni

- Ricerca multipiattaforma: YouTube, Dailymotion e ricerca web filtrata sui siti supportati da yt-dlp (1356 domini).
- Suggerimenti dei siti mentre scrivi nel campo "Piattaforma".
- Anteprima video dentro l'app con player mpv: play/pausa, barra di avanzamento e tempo.
- Download: video + audio, solo video, solo audio MP3.
- Qualità video da 240p a 2160p; qualità audio MP3 da 96 a 320 kbps.
- Cartella di destinazione personalizzabile.

## Requisiti

- Windows 10/11 a 64 bit.
- Connessione internet.

## Note

- I siti che richiedono un account (Vimeo, Instagram, Facebook, ...) possono rifiutare il download: l'app mostra l'errore di yt-dlp.
- La ricerca sui siti non nativi usa un motore web (DuckDuckGo/Google). Se il motore limita le richieste, riprova.
- L'anteprima arriva fino a 720p; il download usa la qualità scelta.

## Sviluppo

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
