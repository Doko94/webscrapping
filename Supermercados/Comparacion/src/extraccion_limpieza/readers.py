import pandas as pd

def read_csv_jumbo(path):
    return pd.read_csv(path, sep=";", encoding="utf-8-sig", engine="python")

def read_csv_robust(path):
    for sep in [",", ";", "\t"]:
        try:
            df = pd.read_csv(path, sep=sep)
            if df.shape[1] > 1:
                return df
        except:
            pass
    return pd.read_csv(path)