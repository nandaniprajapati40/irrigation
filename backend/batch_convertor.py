from pathlib import Path
from mosdac_downloader import mask_hdf5_to_tif

# Paths (same as your structure)
BASE = Path("data/raw")

pet_hdf_dir  = BASE / "insat_pet_hdf"
pet_tif_dir  = BASE / "insat_pet"

rain_hdf_dir = BASE / "insat_rain_hdf"
rain_tif_dir = BASE / "insat_rain"

# ─── PET ─────────────────────────────────────
for hdf in sorted(pet_hdf_dir.glob("*.h5")):
    out = pet_tif_dir / (hdf.stem + ".tif")

    if out.exists():
        print(f"[SKIP PET] {out.name}")
        continue

    try:
        mask_hdf5_to_tif(hdf, out, "pet")
        print(f"[DONE PET] {out.name}")
    except Exception as e:
        print(f"[FAIL PET] {hdf.name} -> {e}")


# ─── RAIN ────────────────────────────────────
for hdf in sorted(rain_hdf_dir.glob("*.h5")):
    out = rain_tif_dir / (hdf.stem + ".tif")

    if out.exists():
        print(f"[SKIP RAIN] {out.name}")
        continue

    try:
        mask_hdf5_to_tif(hdf, out, "rain")
        print(f"[DONE RAIN] {out.name}")
    except Exception as e:
        print(f"[FAIL RAIN] {hdf.name} -> {e}")