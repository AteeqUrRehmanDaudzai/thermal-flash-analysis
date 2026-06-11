#!/usr/bin/env python3
"""Analyze FLIR flash-method videos.

The script isolates flash-induced temperature changes and estimates effective
thermal diffusivity using the Parker half-rise approximation.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


RUNTIME_DEPENDENCIES = {
    "cv2": "opencv-python",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "pandas": "pandas",
}
VIDEO_EXTENSIONS = (".avi", ".mp4", ".mov", ".mkv", ".mpeg", ".mpg")


@dataclass(frozen=True)
class AnalysisConfig:
    sample_thickness_m: float
    output_dir: Path
    roi: tuple[int, int, int, int] | None
    baseline_frames: int
    direct_flash: Path | None
    make_video: bool


@dataclass(frozen=True)
class VideoData:
    frames: np.ndarray
    times_s: np.ndarray
    fps: float


def parse_roi(value: str | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("ROI must be x,y,width,height")
    x, y, width, height = parts
    if min(parts) < 0 or width == 0 or height == 0:
        raise argparse.ArgumentTypeError("ROI values must be non-negative and have positive width/height")
    return x, y, width, height


def read_video(path: Path) -> VideoData:
    import cv2
    import numpy as np

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError(f"Could not open video: {path}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    if not fps or math.isnan(fps) or fps <= 0:
        fps = 1.0

    frames: list[np.ndarray] = []
    times: list[float] = []
    frame_index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
        if timestamp_ms and timestamp_ms > 0:
            times.append(timestamp_ms / 1000.0)
        else:
            times.append(frame_index / fps)
        frames.append(to_grayscale_float(frame))
        frame_index += 1
    capture.release()

    if not frames:
        raise ValueError(f"No frames were read from {path}")

    return VideoData(frames=np.stack(frames), times_s=np.asarray(times), fps=float(fps))


def to_grayscale_float(frame: np.ndarray) -> np.ndarray:
    import cv2
    import numpy as np

    if frame.ndim == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame.astype(np.float32)


def crop_roi(frames: np.ndarray, roi: tuple[int, int, int, int] | None) -> np.ndarray:
    if roi is None:
        return frames
    x, y, width, height = roi
    frame_height, frame_width = frames.shape[1:3]
    if x + width > frame_width or y + height > frame_height:
        raise ValueError(
            f"ROI {roi} exceeds frame dimensions width={frame_width}, height={frame_height}"
        )
    return frames[:, y : y + height, x : x + width]


def detect_flash_index(signal: np.ndarray, baseline_frames: int) -> int:
    import numpy as np

    if signal.size < 3:
        return 0
    derivative = np.diff(signal)
    search_start = min(max(1, baseline_frames // 2), derivative.size - 1)
    flash_index = int(np.argmax(derivative[search_start:]) + search_start + 1)
    return min(flash_index, signal.size - 1)


def baseline_image(frames: np.ndarray, flash_index: int, requested_frames: int) -> np.ndarray:
    import numpy as np

    end = max(1, min(flash_index, requested_frames, frames.shape[0]))
    return np.mean(frames[:end], axis=0)


def subtract_direct_flash(flash_only: np.ndarray, direct_path: Path | None, roi: tuple[int, int, int, int] | None) -> np.ndarray:
    if direct_path is None:
        return flash_only
    import numpy as np

    direct = read_video(direct_path)
    direct_frames = crop_roi(direct.frames, roi)
    usable = min(flash_only.shape[0], direct_frames.shape[0])
    if usable == 0:
        return flash_only
    direct_signal = direct_frames[:usable] - np.mean(direct_frames[: max(1, min(5, usable))], axis=0)
    corrected = flash_only.copy()
    corrected[:usable] = corrected[:usable] - direct_signal
    return corrected


def normalize_response(response: np.ndarray, flash_index: int) -> tuple[np.ndarray, float]:
    import numpy as np

    pre_flash_level = float(np.mean(response[: max(1, flash_index)]))
    post_flash = response[flash_index:]
    peak_level = float(np.max(post_flash)) if post_flash.size else float(np.max(response))
    peak_rise = peak_level - pre_flash_level
    if peak_rise <= 0:
        return np.full_like(response, np.nan, dtype=np.float64), peak_rise
    return (response - pre_flash_level) / peak_rise, peak_rise


def find_half_rise_time(times_s: np.ndarray, normalized: np.ndarray, flash_index: int) -> float:
    for index in range(flash_index, normalized.size):
        if normalized[index] >= 0.5:
            if index == flash_index:
                return 0.0
            previous = index - 1
            y0, y1 = normalized[previous], normalized[index]
            t0, t1 = times_s[previous], times_s[index]
            import numpy as np

            if np.isnan(y0) or np.isnan(y1) or y1 == y0:
                return float(t1 - times_s[flash_index])
            fraction = (0.5 - y0) / (y1 - y0)
            return float((t0 + fraction * (t1 - t0)) - times_s[flash_index])
    return float("nan")


def write_flash_video(path: Path, flash_only: np.ndarray, fps: float) -> None:
    import cv2
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = flash_only.shape[1:3]
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (width, height),
        isColor=False,
    )
    lower, upper = np.percentile(flash_only, [1, 99])
    if upper <= lower:
        upper = lower + 1.0
    scaled = np.clip((flash_only - lower) * 255.0 / (upper - lower), 0, 255).astype(np.uint8)
    for frame in scaled:
        writer.write(frame)
    writer.release()


def analyze_video(path: Path, config: AnalysisConfig, metadata: dict[str, str] | None = None) -> dict[str, object]:
    import pandas as pd

    data = read_video(path)
    roi_frames = crop_roi(data.frames, config.roi)
    raw_response = roi_frames.mean(axis=(1, 2))
    flash_index = detect_flash_index(raw_response, config.baseline_frames)
    baseline = baseline_image(roi_frames, flash_index, config.baseline_frames)
    flash_only = roi_frames - baseline
    flash_only = subtract_direct_flash(flash_only, config.direct_flash, config.roi)
    flash_response = flash_only.mean(axis=(1, 2))
    normalized, peak_rise = normalize_response(flash_response, flash_index)
    t_half_s = find_half_rise_time(data.times_s, normalized, flash_index)
    diffusivity = 0.1388 * config.sample_thickness_m**2 / t_half_s if t_half_s and t_half_s > 0 else float("nan")

    stem = path.stem
    output_dir = config.output_dir / stem if metadata is not None else config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    response_csv = output_dir / f"{stem}_response.csv"
    pd.DataFrame(
        {
            "time_s": data.times_s,
            "raw_roi_mean": raw_response,
            "flash_only_roi_mean": flash_response,
            "normalized_response": normalized,
        }
    ).to_csv(response_csv, index=False)

    plot_path = output_dir / f"{stem}_response.png"
    plot_response(plot_path, data.times_s, flash_response, normalized, flash_index, t_half_s)

    if config.make_video:
        write_flash_video(output_dir / f"{stem}_flash_only.avi", flash_only, data.fps)

    summary: dict[str, object] = {
        "video_name": stem,
        "input_path": str(path),
        "fps": data.fps,
        "frame_count": int(data.frames.shape[0]),
        "roi": config.roi if config.roi is not None else "full_frame",
        "flash_index": flash_index,
        "flash_time_s": float(data.times_s[flash_index]),
        "peak_rise_grayscale_or_temperature_units": peak_rise,
        "t_half_s": t_half_s,
        "sample_thickness_m": config.sample_thickness_m,
        "effective_diffusivity_m2_s": diffusivity,
        "response_csv": str(response_csv),
        "response_plot": str(plot_path),
    }
    if metadata:
        summary.update(metadata)

    summary_csv = output_dir / f"{stem}_summary.csv"
    with summary_csv.open("w", newline="") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)
    return summary


def plot_response(
    path: Path,
    times_s: np.ndarray,
    flash_response: np.ndarray,
    normalized: np.ndarray,
    flash_index: int,
    t_half_s: float,
) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(8, 7))
    axes[0].plot(times_s, flash_response, label="Flash-only ROI mean")
    axes[0].axvline(times_s[flash_index], color="tab:red", linestyle="--", label="Detected flash")
    axes[0].set_ylabel("Signal rise")
    axes[0].legend(loc="best")

    axes[1].plot(times_s - times_s[flash_index], normalized, label="Normalized response")
    axes[1].axhline(0.5, color="tab:gray", linestyle=":", label="Half rise")
    if not math.isnan(t_half_s):
        axes[1].axvline(t_half_s, color="tab:green", linestyle="--", label=f"t1/2={t_half_s:.4g} s")
    axes[1].set_xlabel("Time after flash (s)")
    axes[1].set_ylabel("Normalized rise")
    axes[1].set_ylim(-0.1, 1.1)
    axes[1].legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def find_video(video_dir: Path, video_name: str) -> Path:
    for extension in VIDEO_EXTENSIONS:
        candidate = video_dir / f"{video_name}{extension}"
        if candidate.exists():
            return candidate
    direct_candidate = video_dir / video_name
    if direct_candidate.exists():
        return direct_candidate
    raise FileNotFoundError(f"No video found for {video_name} in {video_dir}")


def manifest_rows(manifest: Path) -> Iterable[dict[str, str]]:
    with manifest.open(newline="") as file_handle:
        yield from csv.DictReader(file_handle)


def run_manifest(args: argparse.Namespace, config: AnalysisConfig) -> None:
    summaries = []
    for row in manifest_rows(args.manifest):
        video_name = row["video_name"]
        try:
            video_path = find_video(args.video_dir, video_name)
        except FileNotFoundError as error:
            print(f"Skipping {video_name}: {error}")
            continue
        print(f"Analyzing {video_path}")
        summaries.append(analyze_video(video_path, config, metadata=row))

    if summaries:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        import pandas as pd

        pd.DataFrame(summaries).to_csv(config.output_dir / "all_summaries.csv", index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze FLIR flash-method videos.")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", type=Path, help="Single video to process.")
    input_group.add_argument("--manifest", type=Path, help="CSV manifest to process.")
    parser.add_argument("--video-dir", type=Path, help="Directory containing manifest videos.")
    parser.add_argument("--sample-thickness-m", type=float, required=True, help="Total package thickness in metres.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for analysis outputs.")
    parser.add_argument("--roi", type=parse_roi, help="ROI as x,y,width,height. Defaults to full frame.")
    parser.add_argument("--baseline-frames", type=int, default=5, help="Maximum pre-flash frames for baseline averaging.")
    parser.add_argument("--direct-flash", type=Path, help="Optional direct-flash reference video to subtract.")
    parser.add_argument("--make-video", action="store_true", help="Write flash-only AVI output.")
    return parser


def missing_runtime_dependencies() -> list[str]:
    return [
        package_name
        for module_name, package_name in RUNTIME_DEPENDENCIES.items()
        if importlib.util.find_spec(module_name) is None
    ]


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.baseline_frames < 1:
        parser.error("--baseline-frames must be at least 1")
    if args.sample_thickness_m <= 0:
        parser.error("--sample-thickness-m must be positive")
    if args.manifest and args.video_dir is None:
        parser.error("--video-dir is required with --manifest")
    missing = missing_runtime_dependencies()
    if missing:
        parser.error(
            "Missing Python dependencies: "
            + ", ".join(missing)
            + ". Install them with: python -m pip install -r thermal_flash_analysis/requirements.txt"
        )

    config = AnalysisConfig(
        sample_thickness_m=args.sample_thickness_m,
        output_dir=args.output_dir,
        roi=args.roi,
        baseline_frames=args.baseline_frames,
        direct_flash=args.direct_flash,
        make_video=args.make_video,
    )

    if args.manifest:
        run_manifest(args, config)
    else:
        analyze_video(args.input, config)


if __name__ == "__main__":
    main()
