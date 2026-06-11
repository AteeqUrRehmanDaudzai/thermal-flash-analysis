# FLIR Flash-Method Thermal Analysis

A standalone thermal flash-method analysis workflow for FLIR thermal videos from photovoltaic module experiments. The workflow extracts flash-only thermal responses and estimates effective thermal diffusivity using the half-rise method.

This repository was separated from the earlier `student-record-storing` repository so the student-record C++ project and the thermal-analysis workflow can be maintained independently.

## Contents

```text
.
|-- README.md
|-- LICENSE
|-- .gitignore
|-- colab/
|   `-- FLIR_flash_analysis_colab.ipynb
`-- thermal_flash_analysis/
    |-- README.md
    |-- analyze_flash.py
    |-- experiment_manifest.csv
    `-- requirements.txt
```

## Quick Start

Install dependencies:

```bash
python -m pip install -r thermal_flash_analysis/requirements.txt
```

Run one video:

```bash
python thermal_flash_analysis/analyze_flash.py \
  --input thermal_flash_analysis/data/raw/FLIR0632.avi \
  --sample-thickness-m 0.0011 \
  --output-dir thermal_flash_analysis/results/FLIR0632 \
  --make-video
```

Run all videos listed in the manifest:

```bash
python thermal_flash_analysis/analyze_flash.py \
  --manifest thermal_flash_analysis/experiment_manifest.csv \
  --video-dir thermal_flash_analysis/data/raw \
  --sample-thickness-m 0.0011 \
  --output-dir thermal_flash_analysis/results \
  --make-video
```

## Google Colab

Open `colab/FLIR_flash_analysis_colab.ipynb` in Google Colab. The notebook installs the required Python packages, mounts Google Drive if needed, runs the thermal analysis script, displays summary tables, and packages outputs for download.

## Notes

- Raw FLIR videos are not included in this repository.
- Put videos in `thermal_flash_analysis/data/raw/` or point the CLI/notebook to your own video directory.
- The diffusivity estimate is an apparent/effective value and should be interpreted with the assumptions described in `thermal_flash_analysis/README.md`.

## License

This project is licensed under the Apache License 2.0. See `LICENSE` for details.
