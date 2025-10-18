#!/usr/bin/env python3
"""
Full Python ShifterCLI
- Converts any video format to .shft fragments
- Generates manifest compatible with ShifterJS
- Supports live, VOD, adaptive bitrate, thumbnails, subtitles
- Incremental fragment naming
- Rolling buffer / auto cleanup
- Resolution names like 720p,1080p,4K,8K
- Cross-platform
"""

import os, sys, json, shutil, subprocess, time
from pathlib import Path
from argparse import ArgumentParser

# ----------------------------
# Helpers
# ----------------------------

def run_ffmpeg(cmd):
    print("[FFmpeg]", " ".join(cmd))
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("FFmpeg Error:", result.stderr.decode())
        sys.exit(1)

def create_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

def incremental_filename(folder, prefix="frag", ext=".shft"):
    existing = sorted(folder.glob(f"{prefix}_*.shft"))
    if existing:
        last = int(existing[-1].stem.split("_")[1])
        return f"{prefix}_{last+1:04d}{ext}"
    else:
        return f"{prefix}_0001{ext}"

# ----------------------------
# Main CLI
# ----------------------------

class ShifterCLI:
    def __init__(self):
        self.parser = self.build_parser()
        self.args = self.parser.parse_args()
        self.output_dir = Path(self.args.output)
        create_dir(self.output_dir)
        self.manifest = {"tag": "live" if self.args.live else "vod", "adaptive": []}

    def build_parser(self):
        parser = ArgumentParser(description="Full Python ShifterCLI")
        parser.add_argument("-i","--input", required=True, help="Input video file or stream")
        parser.add_argument("-o","--output", required=True, help="Output folder")
        parser.add_argument("-r","--resolutions", default="720p,1080p", help="Comma separated resolution names")
        parser.add_argument("-b","--bitrate", default="1000k,3000k", help="Comma separated bitrates for each resolution")
        parser.add_argument("-t","--thumbnails", action="store_true", help="Generate thumbnails")
        parser.add_argument("-s","--subtitles", help="Subtitle file (.vtt)")
        parser.add_argument("-live", action="store_true", help="Enable live streaming mode")
        parser.add_argument("--buffer", type=int, default=5, help="Rolling buffer seconds for live")
        parser.add_argument("--cleanup", action="store_true", help="Automatically remove old fragments")
        return parser

    def parse_resolutions(self):
        res_list = self.args.resolutions.split(",")
        br_list = self.args.bitrate.split(",")
        if len(res_list)!=len(br_list):
            print("Error: resolutions and bitrates must match")
            sys.exit(1)
        return list(zip(res_list, br_list))

    def run(self):
        streams = self.parse_resolutions()
        for res, br in streams:
            res_folder = self.output_dir / res
            create_dir(res_folder)
            fragment_files = []

            # Continuous live mode loop or VOD single run
            running = True
            frag_index = 0
            while running:
                frag_file = res_folder / f"frag_{frag_index+1:04d}.shft"
                ffmpeg_cmd = [
                    "ffmpeg", "-i", self.args.input,
                    "-c:v", "libvpx-vp9", "-b:v", br,
                    "-c:a", "libopus",
                    "-f", "webm",
                    "-map", "0:v:0", "-map", "0:a:0",
                    "-g", "48",
                    "-frames:v", str(self.args.buffer*12), # approximate segment length
                    str(frag_file)
                ]
                run_ffmpeg(ffmpeg_cmd)
                fragment_files.append(str(frag_file))
                frag_index += 1

                # Cleanup old fragments if rolling buffer is enabled
                if self.args.cleanup and len(fragment_files)>12: # keep last 12 fragments
                    old = fragment_files.pop(0)
                    os.remove(old)

                if not self.args.live:
                    running = False
                else:
                    time.sleep(self.args.buffer) # wait buffer duration before next fragment

            # Thumbnails
            thumbnails = []
            if self.args.thumbnails:
                for i, f in enumerate(sorted(res_folder.glob("frag_*.shft"))):
                    thumb_file = res_folder / f"thumb_{i:04d}.webp"
                    ffmpeg_cmd = [
                        "ffmpeg", "-i", str(f),
                        "-vf", "scale=160:90",
                        "-vframes", "1",
                        str(thumb_file)
                    ]
                    run_ffmpeg(ffmpeg_cmd)
                    thumbnails.append(str(thumb_file))

            # Manifest entry
            entry = {
                "resolution": res,
                "bitrate": int(br.replace("k",""))*1000,
                "videoChunks": sorted([str(f) for f in res_folder.glob("frag_*.shft")]),
                "audioChunks": sorted([str(f) for f in res_folder.glob("frag_*.shft")]),
                "thumbnailChunks": thumbnails,
                "subtitleChunks": [self.args.subtitles] if self.args.subtitles else []
            }
            self.manifest["adaptive"].append(entry)

        # Write manifest
        manifest_file = self.output_dir / "manifest.shifter"
        with open(manifest_file, "w") as f:
            json.dump(self.manifest, f, indent=2)
        print(f"Manifest created at: {manifest_file}")

# ----------------------------
# Entry
# ----------------------------
if __name__=="__main__":
    ShifterCLI().run()
                   
