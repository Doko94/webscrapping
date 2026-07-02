import pandas as pd
from config import STANDARD_COLS

def normalize_common(df, supermarket):
    df = df.copy()
    df["supermarket"] = supermarket

    for c in STANDARD_COLS:
        if c not in df.columns:
            df[c] = None

    return df[STANDARD_COLS]