from pathlib import Path
from utils import extract_ts
from datetime import datetime
import pandas as pd

def pick_latest(folder):
    files = list(Path(folder).glob("*.csv"))
    return max(files, key=lambda x: x.stat().st_mtime) if files else None

def consolidate_market(config):
    dfs = []
    selected = []

    for cat in Path(config.output_dir).iterdir():
        if not cat.is_dir():
            continue

        f = pick_latest(cat)
        if not f:
            continue

        df = config.reader(f)
        df["supermercado"] = config.name
        df["categoria"] = cat.name
        df["archivo"] = f.name
        df["ruta_archivo"] = str(f)
        df["timestamp_archivo"] = extract_ts(f.name)

        dfs.append(df)
        selected.append((cat.name, f.name))

    return (pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(), selected)


def export_outputs(df, output_dir, base_name="output"):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    df.to_csv(path / f"{base_name}_{ts}.csv", index=False, encoding="utf-8-sig", sep=";")