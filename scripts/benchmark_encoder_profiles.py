"""Compare FFmpeg profiles on deterministic synthetic video; no source media is retained."""

import argparse
import json
import platform
import re
import shutil
from statistics import median
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clipping.encoding import PROFILES  # noqa: E402


def benchmark(seconds=2, width=540, height=960, repeats=3):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg is required for the local encoder benchmark')
    if (not 1 <= seconds <= 20 or width < 160 or height < 160 or width % 2 or height % 2
            or not 1 <= repeats <= 10):
        raise ValueError('Use 1–20 seconds, 1–10 repeats and even dimensions of at least 160 pixels')
    measurements = {name: [] for name in PROFILES}
    with tempfile.TemporaryDirectory(prefix='content-reward-encoder-') as directory:
        folder = Path(directory)
        source = folder / 'synthetic-source.mkv'
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'lavfi', '-i', f'testsrc2=size={width}x{height}:rate=30',
            '-t', str(seconds), '-an', '-c:v', 'ffv1', '-level', '3', str(source)], check=True)
        names = list(PROFILES)
        for iteration in range(repeats):
            order = names[iteration % len(names):] + names[:iteration % len(names)]
            for name in order:
                options = PROFILES[name]
                output = folder / f'{name}-{iteration}.mp4'
                started = time.perf_counter()
                subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                    '-an', '-c:v', 'libx264', '-threads', '1', '-preset', options['preset'],
                    '-crf', str(options['crf']), str(output)], check=True)
                elapsed = time.perf_counter() - started
                quality = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'info', '-i', str(source),
                    '-i', str(output), '-lavfi', 'psnr', '-f', 'null', '-'],
                    check=True, capture_output=True, text=True).stderr
                match = re.search(r'average:([\d.]+)', quality)
                if not match:
                    raise RuntimeError('ffmpeg did not return an average PSNR measurement')
                measurements[name].append({'elapsed': elapsed, 'bytes': output.stat().st_size,
                                           'psnr': float(match.group(1))})
    results = []
    version = subprocess.run([ffmpeg, '-version'], check=True, capture_output=True, text=True).stdout.splitlines()[0]
    for name, samples in measurements.items():
        options = PROFILES[name]
        elapsed = median(sample['elapsed'] for sample in samples)
        results.append({'profile': name, 'preset': options['preset'], 'crf': options['crf'],
            'elapsed_ms_median': round(elapsed * 1000, 1),
            'realtime_factor_median': round(seconds / elapsed, 3),
            'output_bytes_median': round(median(sample['bytes'] for sample in samples)),
            'psnr_average_db_median': round(median(sample['psnr'] for sample in samples), 4)})
    return {'scope': 'encoder_only_synthetic', 'ffmpeg_version': version,
            'platform': platform.platform(), 'processor': platform.processor(),
            'seconds': seconds, 'repeats': repeats,
            'resolution': f'{width}x{height}', 'fps': 30, 'threads': 1,
            'results': results,
            'note': 'Single-machine synthetic encoder comparison; PSNR is an objective pixel metric, not perceptual or end-to-end quality.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=2)
    parser.add_argument('--width', type=int, default=540)
    parser.add_argument('--height', type=int, default=960)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    try:
        print(json.dumps(benchmark(args.seconds, args.width, args.height, args.repeats), indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
