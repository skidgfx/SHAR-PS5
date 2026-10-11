#!/usr/bin/env python3
"""Convert The Simpsons: Hit & Run's Bink FMVs (.rmv) for the PS5 port.

The PC game's movies are Bink video files with an .rmv extension. The PS5 port
cannot play Bink, so this script converts each one into the port's .shfmv
container (lossless PNG frames + 48 kHz PCM16 stereo audio).

Usage
-----
Prepare a title folder in one step (recommended):

    python convert_fmv.py --install PPSA99317

  This converts every PPSA99317/assets/movies/*.rmv into a lower-case
  PPSA99317/assets/movies/<name>.shfmv next to it, then rewrites
  PPSA99317/shar_files.txt (the file list the game uses to find its data on
  the console). Already converted movies are skipped, so it can be re-run
  after an interruption. Add --delete-rmv to remove the .rmv originals from
  the title folder once they are converted (saves ~1 GB on the console).

Only rebuild shar_files.txt (after adding or removing files by hand):

    python convert_fmv.py --install PPSA99317 --manifest-only

Convert a file or a folder somewhere else:

    python convert_fmv.py path/to/movies  path/to/output     # -> output/movies/*.shfmv
    python convert_fmv.py path/to/fmv1A.rmv path/to/output   # -> output/fmv1a.shfmv

Requirements: Python 3.8+ and FFmpeg (ffmpeg + ffprobe) with Bink decoding,
which every standard FFmpeg build has. FFmpeg is used only here, on your
computer; nothing of it goes onto the console.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile


MAGIC = b"SHARFMV1"
HEADER = struct.Struct("<8s7IQ")
INDEX = struct.Struct("<QI")
AUDIO_RATE = 48000

# PC-only files the PS5 build never reads: left out of shar_files.txt.
SKIP = ("*.exe", "*.dll", "*.map", "*.ilk", "*.lib", "*.exp", "*.pdb",
        "save*", "simpsons.ini", "*.partial")


def run(command: list[str]) -> bytes:
    return subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout


_passthrough: list[str] = []


def passthrough_option(ffmpeg: str) -> list[str]:
    """Keep every decoded frame: -fps_mode (FFmpeg 5.1+) or -vsync (older builds)."""
    if not _passthrough:
        help_text = subprocess.run([ffmpeg, "-hide_banner", "-h", "long"], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT).stdout.decode("utf-8", "replace")
        _passthrough.extend(["-fps_mode", "passthrough"] if "-fps_mode" in help_text
                            else ["-vsync", "passthrough"])
    return _passthrough


def find_tool(name: str, given: str | None) -> str:
    tool = given or shutil.which(name)
    if not tool or not shutil.which(tool):
        sys.exit(f"convert_fmv: '{given or name}' not found. Install FFmpeg (it includes {name}) and "
                 f"make sure it is on your PATH, or pass --{name} C:\\path\\to\\{name}.exe.\n"
                 "  Windows: winget install Gyan.FFmpeg   macOS: brew install ffmpeg   "
                 "Debian/Ubuntu: sudo apt install ffmpeg")
    return tool


# --------------------------------------------------------------------------
# conversion
# --------------------------------------------------------------------------

def convert(source: Path, destination: Path, ffmpeg: str, ffprobe: str) -> None:
    info = json.loads(run([
        ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height,r_frame_rate", "-of", "json", str(source),
    ]))
    streams = info.get("streams", [])
    if not streams:
        raise ValueError(f"no video stream: {source}")
    video = streams[0]
    width, height = int(video["width"]), int(video["height"])
    fps_num, fps_den = map(int, video["r_frame_rate"].split("/"))
    if not (0 < width <= 4096 and 0 < height <= 4096 and fps_num and fps_den):
        raise ValueError(f"invalid video dimensions or frame rate: {source}")

    audio_info = json.loads(run([
        ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
        "stream=index", "-of", "json", str(source),
    ]))
    has_audio = bool(audio_info.get("streams"))

    with tempfile.TemporaryDirectory(prefix="shar-fmv-") as temp_name:
        temp = Path(temp_name)
        pattern = temp / "frame-%08d.png"
        run([
            ffmpeg, "-v", "error", "-i", str(source), "-map", "0:v:0",
            *passthrough_option(ffmpeg), "-start_number", "0", str(pattern),
        ])
        frames = sorted(temp.glob("frame-*.png"))
        if not frames:
            raise ValueError(f"decoder produced no video frames: {source}")

        pcm_path = temp / "audio.pcm"
        channels = 0
        samples = 0
        if has_audio:
            run([
                ffmpeg, "-v", "error", "-i", str(source), "-map", "0:a:0",
                # Bink audio can carry non-monotonic packet timestamps. Rebuild
                # timestamps from decoded sample counts to keep all PCM output.
                "-vn", "-af", "asetpts=N/SR/TB", "-ac", "2", "-ar", str(AUDIO_RATE),
                "-c:a", "pcm_s16le", "-f", "s16le", str(pcm_path),
            ])
            channels = 2
            samples = pcm_path.stat().st_size // (channels * 2)

        table_end = HEADER.size + len(frames) * INDEX.size
        cursor = table_end
        frame_entries: list[tuple[int, int]] = []
        for frame in frames:
            size = frame.stat().st_size
            frame_entries.append((cursor, size))
            cursor += size

        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".partial")
        try:
            with partial.open("wb") as out:
                out.write(HEADER.pack(
                    MAGIC, width, height, fps_num, fps_den, len(frames),
                    AUDIO_RATE if has_audio else 0, channels, samples,
                ))
                for offset, size in frame_entries:
                    out.write(INDEX.pack(offset, size))
                for frame in frames:
                    with frame.open("rb") as stream:
                        shutil.copyfileobj(stream, out)
                if has_audio:
                    with pcm_path.open("rb") as stream:
                        shutil.copyfileobj(stream, out)
            os.replace(partial, destination)
        finally:
            if partial.exists():
                partial.unlink()
    print(f"  {source.name} -> {destination.name} ({len(frames)} frames, {width}x{height}, "
          f"audio={'yes' if has_audio else 'no'}, {destination.stat().st_size / 2**20:.0f} MB)", flush=True)


def is_valid_shfmv(path: Path) -> bool:
    """True when path is a complete .shfmv file (header + index + data fit the size)."""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            head = f.read(HEADER.size)
            if len(head) != HEADER.size:
                return False
            magic, w, h, fn, fd, count, rate, ch, samples = HEADER.unpack(head)
            if magic != MAGIC or count == 0:
                return False
            f.seek(HEADER.size + (count - 1) * INDEX.size)
            offset, length = INDEX.unpack(f.read(INDEX.size))
        return offset + length + samples * ch * 2 == size
    except (OSError, struct.error):
        return False


def rmv_files(folder: Path) -> list[Path]:
    # The disc mixes case (fmv1A.rmv): match .rmv in any case.
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".rmv")


# --------------------------------------------------------------------------
# title folder
# --------------------------------------------------------------------------

def skipped(name: str) -> bool:
    return any(fnmatch.fnmatch(name.lower(), p) for p in SKIP)


def write_manifest(assets: Path, out: Path) -> int:
    """shar_files.txt: every data file, relative to assets/, '/' separators, real case.

    The console's directory listings are unreliable, so the game's case-insensitive
    path resolver reads this list instead (it must sit next to eboot.bin).
    """
    rows = []
    for root, dirs, files in os.walk(assets):
        dirs[:] = sorted(d for d in dirs if not skipped(d))
        rel = os.path.relpath(root, assets).replace(os.sep, "/")
        for name in sorted(files):
            if not skipped(name):
                rows.append(name if rel == "." else f"{rel}/{name}")
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(rows) + "\n")
    return len(rows)


def install(title: Path, ffmpeg: str | None, ffprobe: str | None,
            delete_rmv: bool, manifest_only: bool, force: bool) -> int:
    title = title.resolve()
    assets = title / "assets"
    if not (title / "eboot.bin").is_file():
        sys.exit(f"convert_fmv: {title} has no eboot.bin - point --install at the PPSA99317 folder")
    if not assets.is_dir():
        sys.exit(f"convert_fmv: {assets} not found - copy your game files into it first (see README)")
    if not (assets / "art").is_dir():
        print(f"WARNING: {assets} has no art/ folder - the game data seems to be missing or one "
              "folder level too deep (assets/ should contain art/, movies/, scripts/, sound/ ...).")
    pc_only = [p.name for p in assets.iterdir() if skipped(p.name)]
    if pc_only:
        print(f"note: PC-only files in assets/ (not needed on the PS5, you may delete them): "
              f"{', '.join(sorted(pc_only))}")

    failed: list[str] = []
    if not manifest_only:
        movies = next((p for p in assets.iterdir() if p.is_dir() and p.name.lower() == "movies"), None)
        sources = rmv_files(movies) if movies else []
        if not sources:
            print("WARNING: no .rmv movies found in assets/movies - nothing to convert.")
        else:
            ffmpeg_exe, ffprobe_exe = find_tool("ffmpeg", ffmpeg), find_tool("ffprobe", ffprobe)
            print(f"Converting {len(sources)} movies in {movies} (this takes a while; ~5 GB of output) ...")
            for i, source in enumerate(sources, 1):
                # The game asks for lower-case names (movies/fmv1a) and the PS5
                # file system is case-sensitive: write lower-case output names.
                target = source.with_name(source.stem.lower() + ".shfmv")
                print(f"[{i}/{len(sources)}] {source.name}", flush=True)
                if not force and is_valid_shfmv(target):
                    print(f"  {target.name} already converted - skipped")
                else:
                    try:
                        convert(source, target, ffmpeg_exe, ffprobe_exe)
                    except (OSError, ValueError, KeyError, ZeroDivisionError,
                            subprocess.CalledProcessError) as error:
                        print(f"  FAILED: {error}")
                        failed.append(source.name)
                        continue
                if delete_rmv:
                    source.unlink()
                    print(f"  deleted {source.name}")

    count = write_manifest(assets, title / "shar_files.txt")
    print(f"\nWrote {title / 'shar_files.txt'} ({count} data files).")
    if failed:
        print(f"{len(failed)} movie(s) FAILED: {', '.join(failed)} - fix the error above and re-run "
              "(finished movies are skipped).")
        return 1
    print(f"Done. Copy the whole {title.name} folder to /data/homebrew/ on your PS5.")
    return 0


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, nargs="?", help="Bink .rmv file or folder")
    parser.add_argument("destination", type=Path, nargs="?", help="output .shfmv file or folder")
    parser.add_argument("--install", type=Path, metavar="PPSA_FOLDER",
                        help="convert the movies inside a title folder and rewrite its shar_files.txt")
    parser.add_argument("--delete-rmv", action="store_true",
                        help="with --install: delete each .rmv from the title folder after converting it")
    parser.add_argument("--manifest-only", action="store_true",
                        help="with --install: only rewrite shar_files.txt")
    parser.add_argument("--force", action="store_true", help="re-convert movies that are already done")
    parser.add_argument("--ffmpeg", help="ffmpeg executable (default: from PATH)")
    parser.add_argument("--ffprobe", help="ffprobe executable (default: from PATH)")
    args = parser.parse_args()

    if args.install:
        if args.source or args.destination:
            parser.error("use either --install PPSA_FOLDER or SOURCE DESTINATION, not both")
        return install(args.install, args.ffmpeg, args.ffprobe, args.delete_rmv,
                       args.manifest_only, args.force)
    if not (args.source and args.destination):
        parser.error("give SOURCE and DESTINATION, or --install PPSA_FOLDER")

    ffmpeg, ffprobe = find_tool("ffmpeg", args.ffmpeg), find_tool("ffprobe", args.ffprobe)
    try:
        if args.source.is_dir():
            # Keep the source folder name, so movies/ in -> output/movies/*.shfmv out.
            output_root = args.destination / args.source.name
            for source in rmv_files(args.source):
                relative = Path(str(source.relative_to(args.source).with_suffix(".shfmv")).lower())
                target = output_root / relative
                if not args.force and is_valid_shfmv(target):
                    print(f"  {target.name} already converted - skipped")
                    continue
                convert(source, target, ffmpeg, ffprobe)
        else:
            destination = args.destination
            if destination.is_dir() or not destination.suffix:
                destination = destination / args.source.with_suffix(".shfmv").name.lower()
            convert(args.source, destination, ffmpeg, ffprobe)
    except (OSError, ValueError, subprocess.CalledProcessError, KeyError, ZeroDivisionError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
