# Event photo grouping

Sort a mixed folder of event photos into named groups (Stage, Decoration, Guests, and so on) on your own PC. Photos are copied, not moved. Nothing is uploaded.

## What you need

- Windows 10 or 11, 64-bit
- Python 3.11 or newer (checked on 3.14)
- 8 GB RAM (16 GB is more comfortable)
- About 5 GB free disk for Python, the model, and the copied photos
- Internet once, to install libraries and download the model (about 400 MB)

A GPU is optional. The commands below install the CPU build of PyTorch.

## Setup

In PowerShell, from this folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

If `py -3` is not found, install Python from [python.org](https://www.python.org/downloads/) and try again.

Libraries:

| Package | Role |
| --- | --- |
| torch, torchvision | Run the vision model on CPU |
| transformers, sentencepiece | Load SigLIP (`google/siglip-base-patch16-224`) |
| pillow, pillow-heif | Read JPEG, PNG, WEBP, and iPhone HEIC |
| numpy | Compare photo and category vectors |
| pyyaml | Category list |
| tqdm | Progress while embedding |
| streamlit | Local gallery in the browser |
| customtkinter | Rounded window for choosing folders and sorting |

## Sort a folder

Open the small window, browse to the mixed photo folder, browse to an output folder, then click **Sort photos**:

```powershell
python -m src.gui
```

The same sort can be started from the command line:

```powershell
python -m src.cli --input D:\Events\Wedding\all --output D:\Events\Wedding\sorted
```

`--input` is the mixed folder. `--output` must be a different folder. Each run replaces the group folders inside `--output` and writes `manifest.csv` there. Image vectors are saved in `sorted\.cache`, so a second run only embeds new or changed files.

Open `sorted\Stage` (or whichever group you need) in File Explorer. Photos that match more than one group are copied into each of those folders. Weak matches go to `Needs review`.

Useful options:

```powershell
python -m src.cli --input D:\Events\Wedding\all --output D:\Events\Wedding\sorted --threshold 0.08 --batch-size 4
```

- `--threshold` overrides `min_score` in [config/categories.yaml](config/categories.yaml)
- `--batch-size` lowers memory use (try 2 or 4 on an 8 GB PC)
- `--device cpu` forces CPU even if an NVIDIA GPU is present

The first run downloads the model into the Hugging Face cache. Later runs work offline.

On CPU, a few hundred photos often take several minutes the first time.

## Browse in the browser

```powershell
streamlit run app.py
```

Choose the sorted folder in the sidebar. Pick a group to see its photos, or search with words such as `stage`, `mandap`, or `flowers`. Search uses the same SigLIP scores as the sorter. The first search loads the model; browsing groups does not.

## Change the groups

Edit [config/categories.yaml](config/categories.yaml). Each entry needs a folder `name` and a `prompt` that describes the photo you want in that group. Then run the sorter again. Cached image vectors are reused; only the labels are recalculated.

## How a photo is filed

SigLIP turns each photo and each prompt into a vector and scores them independently from 0 to 1. Every prompt at or above `min_score` gets a copy of the photo. The highest score is the primary group, listed first in `manifest.csv`. If every score is below `min_score`, the only copy is in the review folder.
