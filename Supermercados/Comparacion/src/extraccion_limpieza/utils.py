from datetime import datetime
from config import TS_RE

def extract_ts(fname: str):
    m = TS_RE.search(fname)
    if not m:
        return None
    ts = m.group("date") + m.group("time")
    return datetime.strptime(ts, "%Y%m%d%H%M%S")