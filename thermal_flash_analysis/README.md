# FLIR flash-method thermal analysis

This folder contains a reproducible workflow for FLIR thermal videos from photovoltaic module flash experiments.

The workflow is designed for two goals:

1. Visualize the flash-only thermal signal by removing the pre-flash thermal background from every frame and optionally subtracting a direct-flash/reference acquisition.
2. Estimate effective thermal diffusivity from the rear-face thermal response using the flash-method half-rise time.

## Experiment Map

The file `experiment_manifest.csv` records the FLIR0626 through FLIR0650 experiment log, including sample type, repetition number, flash energy configuration, and the uncertain FLIR0638 run.

| Configuration | Flash setting | Videos | Samples |
|---|---|---|---|
| 1 | Yellow 8, Green 1/1 | FLIR0626-FLIR0638 | Glass, ITO, PVK semitransparent, PVK opaque |
| 2 | Yellow 4, Green 1/16 | FLIR0639-FLIR0650 | Reverse-order PVK opaque, PVK semitransparent, ITO, Glass |

## Google Colab Quick Start

A ready-to-edit notebook is included at `colab/FLIR_flash_analysis_colab.ipynb`.

1. Open Google Colab and choose **File > Open notebook > GitHub**.
2. Paste this repository URL: `https://github.com/AteeqUrRehmanDaudzai/thermal-flash-analysis`.
3. Open `colab/FLIR_flash_analysis_colab.ipynb`.
4. Put exported FLIR videos in Google Drive, for example `MyDrive/FLIR_flash/data/raw/FLIR0626.avi` through `FLIR0650.avi`.
5. Set `VIDEO_DIR`, `OUTPUT_DIR`, `SAMPLE_THICKNESS_M`, and optional `ROI`, then run the notebook cells.

## Input Video Preparation

Place videos in a folder such as `thermal_flash_analysis/data/raw/`. OpenCV-readable files such as `.avi`, `.mp4`, `.mov`, and some FLIR-exported video formats are supported directly. If the original FLIR files are radiometric `.seq`/`.fff` files, export them first to a temperature image sequence or video from FLIR software, or convert them with a FLIR radiometric tool before using this script.

Recommended folder layout:

```text
thermal_flash_analysis/
  analyze_flash.py
  experiment_manifest.csv
  data/raw/FLIR0626.avi
  data/raw/FLIR0627.avi
  ...
```

## Quick Start

Install dependencies:

```bash
python -m pip install -r thermal_flash_analysis/requirements.txt
```

Run one video and write a flash-only video, plots, and CSV output:

```bash
python thermal_flash_analysis/analyze_flash.py \
  --input thermal_flash_analysis/data/raw/FLIR0632.avi \
  --sample-thickness-m 0.0011 \
  --output-dir thermal_flash_analysis/results/FLIR0632 \
  --make-video
```

Run all listed videos in a folder:

```bash
python thermal_flash_analysis/analyze_flash.py \
  --manifest thermal_flash_analysis/experiment_manifest.csv \
  --video-dir thermal_flash_analysis/data/raw \
  --sample-thickness-m 0.0011 \
  --output-dir thermal_flash_analysis/results \
  --make-video
```

If you have a direct flash acquisition without the sample, subtract it:

```bash
python thermal_flash_analysis/analyze_flash.py \
  --input thermal_flash_analysis/data/raw/FLIR0632.avi \
  --direct-flash thermal_flash_analysis/data/raw/direct_flash.avi \
  --sample-thickness-m 0.0011 \
  --output-dir thermal_flash_analysis/results/FLIR0632 \
  --make-video
```

## Region of Interest

By default, the script uses the whole frame. For real experiments, pass an ROI that covers only the active cell area and excludes clips, supports, reflections, and frame borders:

```bash
--roi x,y,width,height
```

Example:

```bash
--roi 120,80,260,210
```

## Thermal Diffusivity Calculation

For each video, the script:

1. Reads the frame timestamps or derives time from FPS.
2. Computes a pre-flash baseline from frames before the detected flash.
3. Creates a flash-only signal: `frame - baseline`.
4. Extracts the ROI mean rear-face response versus time.
5. Detects the flash onset from the maximum positive derivative.
6. Normalizes the post-flash response between pre-flash baseline and peak temperature rise.
7. Finds `t_half`, the time after flash onset where the normalized response reaches 0.5.
8. Estimates effective thermal diffusivity with Parker's half-rise approximation:

```text
alpha = 0.1388 * L^2 / t_half
```

where `L` is the total measured module/package thickness in metres and `alpha` is in square metres per second.

Because pulse duration and experimental configuration can bias the result, treat the first output as an apparent/effective diffusivity. Use direct-flash subtraction and compare both flash settings to assess finite-pulse bias.

## Outputs

For each processed video the script writes:

- `*_response.csv`: time, raw ROI mean, flash-only ROI mean, and normalized response.
- `*_summary.csv`: flash index/time, peak rise, half-rise time, effective diffusivity, ROI, FPS, and frame count.
- `*_response.png`: thermal response plot with flash and half-rise markers.
- `*_flash_only.avi` if `--make-video` is set.

For manifest runs, `all_summaries.csv` is also written and can be grouped by sample/configuration for repeatability.

## Quality Checks

- Confirm the ROI is fully inside the cell and not on the laser support.
- Inspect `*_flash_only.avi` to verify that the signal is from the flash through the sample, not camera auto-scaling or reflections.
- Check that the response reaches a clear peak and half-rise crossing.
- Flag FLIR0638 separately until its response agrees with FLIR0635-FLIR0637.
- Compare repetitions within each sample/configuration; large scatter usually means motion, saturation, bad ROI, incomplete capacitor recovery, or pulse-energy variation.
