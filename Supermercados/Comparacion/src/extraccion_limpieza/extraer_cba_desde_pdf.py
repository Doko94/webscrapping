from pathlib import Path
import re
import pdfplumber
import pandas as pd


# =========================================================
# RUTAS
# =========================================================
SCRIPT_DIR = Path(__file__).resolve().parent
# .../Supermercados
SUPERMERCADOS_DIR = SCRIPT_DIR.parents[2]

PDF_PATH = SUPERMERCADOS_DIR / "CBA" / "Valor_CBA_y_LPs_25.12.pdf"

# Guardar dentro de Comparacion/src/output
OUTPUT_DIR = SCRIPT_DIR.parent / "output" / "out_cba"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_CSV = OUTPUT_DIR / "cba_anexo1_diciembre2025.csv"

# Páginas del PDF donde está el Anexo 1 (1-indexed)
TARGET_PAGES = [11, 12]

# =========================================================
# REGEX FILAS
# nombre alimento | unidad | cantidad_dia | calorias_dia | valor_mes
# =========================================================
ROW_RE = re.compile(
    r"^(?P<alimento>.+?)\s+"
    r"(?P<unidad>G|CC)\s+"
    r"(?P<cantidad>\d+(?:,\d+)?)\s+"
    r"(?P<calorias>\d+(?:,\d+)?)\s+"
    r"(?P<valor>\d{1,3}(?:\.\d{3})*,\d+)$"
)

SKIP_PATTERNS = [
    r"^diciembre 2025$",
    r"^Anexo 1:",
    r"^Alimento\s+Unidad",
    r"^Cantidad",
    r"^Calor[ií]as",
    r"^Valor",
    r"^\(D[ií]a\)$",
    r"^\(Mes\)$",
    r"^\d+$",
    r"^Fuente:",
]


# =========================================================
# HELPERS
# =========================================================
def should_skip(line: str) -> bool:
    line = line.strip()
    if not line:
        return True
    return any(re.search(pat, line, flags=re.IGNORECASE) for pat in SKIP_PATTERNS)


def parse_number_cl(x: str) -> float:
    """
    Convierte número chileno:
    1.412,3 -> 1412.3
    22,2 -> 22.2
    """
    return float(x.replace(".", "").replace(",", "."))


def clean_alimento_text(text: str) -> str:
    """
    Limpia basura residual del PDF, por ejemplo:
    '(Día) (Día) (Mes) Arroz' -> 'Arroz'
    """
    if text is None:
        return ""

    s = str(text).strip()

    # remover repeticiones al inicio tipo "(Día) (Día) (Mes)"
    s = re.sub(
        r"^(?:\((?:D[ií]a|Mes)\)\s*)+",
        "",
        s,
        flags=re.IGNORECASE
    )

    # por seguridad, elimina cualquier '(Día)' o '(Mes)' suelto al inicio
    s = re.sub(
        r"^(?:D[ií]a|Mes|\((?:D[ií]a|Mes)\))\s*",
        "",
        s,
        flags=re.IGNORECASE
    )

    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_lines_from_pages(pdf_path: Path, target_pages: list[int]) -> list[str]:
    lines = []

    with pdfplumber.open(pdf_path) as pdf:
        for p in target_pages:
            page = pdf.pages[p - 1]
            text = page.extract_text()
            if not text:
                continue

            page_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            lines.extend(page_lines)

    return lines


def normalize_wrapped_lines(lines: list[str]) -> list[str]:
    """
    Une líneas partidas por salto visual del PDF.

    Ejemplo:
    Tostadas (palta o mantequilla o mermelada o mezcla de
    estas) - para desayuno G 0,0 0,1 5,6
    """
    merged = []
    buffer = None

    for line in lines:
        if should_skip(line):
            continue

        if buffer is None:
            if ROW_RE.match(line):
                merged.append(line)
            else:
                buffer = line
        else:
            candidate = f"{buffer} {line}"

            if ROW_RE.match(candidate):
                merged.append(candidate)
                buffer = None
            else:
                buffer = candidate

    if buffer and ROW_RE.match(buffer):
        merged.append(buffer)

    return merged


def parse_rows(lines: list[str]) -> list[dict]:
    rows = []

    for line in lines:
        m = ROW_RE.match(line)
        if not m:
            continue

        alimento = clean_alimento_text(m.group("alimento").strip())

        rows.append(
            {
                "Alimento": alimento,
                "Unidad": m.group("unidad").strip(),
                "Cantidad_dia": parse_number_cl(m.group("cantidad")),
                "Calorias_dia": parse_number_cl(m.group("calorias")),
                "Valor_mensual": parse_number_cl(m.group("valor")),
            }
        )

    return rows


# =========================================================
# MAIN
# =========================================================
def main():
    print(f"[INFO] Buscando PDF en: {PDF_PATH}")

    if not PDF_PATH.exists():
        raise FileNotFoundError(f"No se encontró el PDF: {PDF_PATH}")

    raw_lines = extract_lines_from_pages(PDF_PATH, TARGET_PAGES)
    merged_lines = normalize_wrapped_lines(raw_lines)
    rows = parse_rows(merged_lines)

    if not rows:
        raise ValueError("No se extrajeron filas. Revisa el PDF o las páginas objetivo.")

    df = pd.DataFrame(
        rows,
        columns=["Alimento", "Unidad", "Cantidad_dia", "Calorias_dia", "Valor_mensual"]
    )

    df.to_csv(OUTPUT_CSV, sep=";", index=False, encoding="utf-8-sig")

    print(f"[OK] CSV generado: {OUTPUT_CSV}")
    print(f"[INFO] Filas extraídas: {len(df)}")
    print(df.head(10))


if __name__ == "__main__":
    main()