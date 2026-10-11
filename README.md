# The Simpsons: Hit & Run — PS5 port

An unofficial port of *The Simpsons: Hit & Run* (2003) to the PlayStation 5, running as a homebrew title.

**No game content is included.** This repository and its release contain no art, audio, video, scripts or other data from the original game. You need your own copy of the PC version of *The Simpsons: Hit & Run*. Everything the game needs is copied from that copy onto your PS5 by you.

---

## What you need

- A PS5 that can run homebrew titles (a loader such as ShadowMountPlus) and a way to copy files to it (the homebrew FTP server, or USB plus a file manager).
- Your own **PC copy of The Simpsons: Hit & Run**, installed from your own disc.
- The `PPSA99317` title folder from this repository's **Releases** page.
- A computer (Windows, macOS or Linux) with:
  - **Python 3.8 or newer**: https://www.python.org/downloads/ (on Windows, tick "Add python.exe to PATH" during setup).
  - **FFmpeg**, which converts the movies:
    - Windows: `winget install Gyan.FFmpeg` (or download it from https://www.gyan.dev/ffmpeg/builds/ and add its `bin` folder to PATH)
    - macOS: `brew install ffmpeg`
    - Debian/Ubuntu: `sudo apt install ffmpeg`
- About **15 GB of free disk space**: ~3.7 GB of game data plus ~5 GB of converted movies, with room to spare.

Open a new terminal and check that both work:

```
python --version
ffmpeg -version
```

(On macOS/Linux the command may be `python3`.)

---

## Step 1 — Download the title folder

Download the release zip and extract it. You get one folder:

```
PPSA99317/
├── eboot.bin
├── sce_module/
├── sce_sys/
└── shar_files.txt
```

## Step 2 — Copy your game files into `PPSA99317/assets/`

1. Create a folder named `assets` inside `PPSA99317`.
2. Find your installed game folder, the one with `Simpsons.exe` in it. To get there, right-click the game's shortcut and choose **Open file location**.
3. Copy **everything in that folder** into `PPSA99317/assets/`.

When you're done it should look like this. The `art`, `movies`, `scripts` and `sound` folders and the `.rcf` files must sit directly inside `assets/`, not one folder further down:

```
PPSA99317/
├── eboot.bin
├── sce_module/
├── sce_sys/
├── shar_files.txt
└── assets/
    ├── art/
    ├── movies/         <- fmv1A.rmv, intro.rmv, ...
    ├── scripts/
    ├── sound/
    ├── ambience.rcf, carsound.rcf, dialog.rcf, music.rcf, ...
    └── Simpsons.exe, *.dll, ...   (not needed on the PS5, you can delete them)
```

The PS5 build never uses the PC program files (`*.exe`, `*.dll`), the `Save*` folders or `simpsons.ini`. You can leave them out to save space.

## Step 3 — Convert the movies

The game's movies (`assets/movies/*.rmv`) are in RAD Game Tools' proprietary **Bink** video format, which the PS5 port can't play. `convert_fmv.py` turns each one into the port's own `.shfmv` format, then rebuilds `shar_files.txt`, the list of files the game uses to find its data on the console.

Download `convert_fmv.py` from this repository and run it on the title folder:

```
python convert_fmv.py --install path/to/PPSA99317
```

- This takes a while: 16 movies, ~5 GB of output. If it's interrupted, run it again and the movies already converted are skipped.
- Add `--delete-rmv` to delete each original `.rmv` from the title folder once it's converted. This saves ~1 GB on the console. Your installed game isn't touched.
- If FFmpeg isn't on your PATH, point to it: `--ffmpeg C:\ffmpeg\bin\ffmpeg.exe --ffprobe C:\ffmpeg\bin\ffprobe.exe`.

> **Always run the script (at least with `--manifest-only`) after changing files in `assets/`.** The game only sees files listed in `shar_files.txt`. If you add, rename or delete files by hand, rebuild the list with:
> `python convert_fmv.py --install path/to/PPSA99317 --manifest-only`

## Step 4 — Copy to the PS5 and launch

1. Copy the whole `PPSA99317` folder to `/data/homebrew/PPSA99317/` on the console (FTP or USB).
2. Register and launch it like your other homebrew titles. Launch it as a registered title; don't send `eboot.bin` to an ELF loader.

Saves are written to the title's own download data on the console.

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `'ffmpeg' not found` | Install FFmpeg (see above) and open a **new** terminal, or pass `--ffmpeg` / `--ffprobe` with full paths. |
| `has no art/ folder` warning | Your files are one folder too deep (e.g. `assets/The Simpsons Hit & Run/art`). Move them up so `art/` is directly inside `assets/`. |
| Game starts but movies are skipped / black | Run step 3 again and check that it finished without `FAILED` lines, then copy the new `.shfmv` files **and** `shar_files.txt` to the console. |
| Game can't find a file / crashes on load | Rebuild `shar_files.txt` with `--manifest-only` and copy it next to `eboot.bin` on the console. |
| Title does not appear or won't start | Report your firmware version, your loader, and `shar.log` (the game writes it to its `/download0` folder, usually `/user/download/PPSA99317/shar.log`). |

## The `.shfmv` format

All integers are little-endian, with no padding.

| Field | Type | Meaning |
| --- | --- | --- |
| magic | 8 bytes | ASCII `SHARFMV1` |
| width, height | u32, u32 | video size |
| fps numerator, denominator | u32, u32 | constant frame rate |
| frame count | u32 | number of PNG frames |
| audio rate | u32 | 48000, or 0 without audio |
| audio channels | u32 | 2, or 0 without audio |
| audio sample frames | u64 | number of stereo sample frames |
| frame index | `frame count` × (`offset:u64`, `size:u32`) | absolute byte range of each PNG |
| frames | variable | PNG images in index order |
| audio | variable | interleaved signed 16-bit PCM stereo, if present |

---

## Legal

*The Simpsons: Hit & Run* is © 2003 Fox Interactive / Vivendi Universal Games, developed by Radical Entertainment. *The Simpsons* is a trademark of Twentieth Century Fox Film Corporation. Bink is a trademark of RAD Game Tools / Epic Games. This project isn't affiliated with or endorsed by any of them.

This project doesn't distribute any of the game's content. Use it only with a copy of the game you legally own. Don't open issues or pull requests containing game files, and don't ask for them.
