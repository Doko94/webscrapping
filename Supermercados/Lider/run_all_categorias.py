import csv
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List


# --------------------------------------------------
# CONFIG
# --------------------------------------------------
MAX_WORKERS = 1
TIMEOUT_SECONDS = None

BASE_DIR = Path(__file__).resolve().parent
CATEGORIAS_DIR = BASE_DIR / "src/categorias"
LOGS_DIR = BASE_DIR / "logs_runs"

SCRIPTS_TO_RUN = [
    "lider_bebes_jugueteria.py",
    # "lider_bebidas_snack.py",
    # "lider_carnes_pescados.py",
    # "lider_chocolates.py",
    # "lider_colaciones.py",
    # "lider_congelados.py",
    # "lider_desayunos_dulces.py",
    # "lider_despensa.py",
    # "lider_frescos_lacteos.py",
    # "lider_frutas_verduras.py",
    # "lider_higiene_cuidado_personal.py",
    # "lider_la_boti.py",
    # "lider_limpieza_aseo.py",
    # "lider_mascota.py",
    # "lider_panaderia_pasteleria.py",
]


@dataclass
class RunResult:
    script_name: str
    status: str
    return_code: int
    duration_sec: int
    stdout_log: str
    stderr_log: str
    stderr_tail: str = ""
    error: str = ""


def run_one_script(script_path: Path, run_id: str) -> RunResult:
    script_name = script_path.name

    run_dir = LOGS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    stdout_log = run_dir / f"{script_name}.out.log"
    stderr_log = run_dir / f"{script_name}.err.log"

    start_time = time.time()

    # Forzar UTF-8 para el proceso hijo (evita UnicodeEncodeError por emojis/acentos)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            env=env
        )

        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""

        stdout_log.write_text(stdout_text, encoding="utf-8", errors="replace")
        stderr_log.write_text(stderr_text, encoding="utf-8", errors="replace")

        status = "OK" if proc.returncode == 0 else "ERROR"
        tail_err = "\n".join(stderr_text.splitlines()[-30:]) if stderr_text else ""

        return RunResult(
            script_name=script_name,
            status=status,
            return_code=proc.returncode,
            duration_sec=int(time.time() - start_time),
            stdout_log=str(stdout_log),
            stderr_log=str(stderr_log),
            stderr_tail=tail_err,
        )

    except subprocess.TimeoutExpired as e:
        stderr_log.write_text(f"TIMEOUT: {TIMEOUT_SECONDS}s\n{e}", encoding="utf-8", errors="replace")
        return RunResult(
            script_name=script_name,
            status="TIMEOUT",
            return_code=124,
            duration_sec=int(time.time() - start_time),
            stdout_log=str(stdout_log),
            stderr_log=str(stderr_log),
            stderr_tail=f"TIMEOUT: {TIMEOUT_SECONDS}s",
            error=str(e),
        )

    except Exception as e:
        stderr_log.write_text(str(e), encoding="utf-8", errors="replace")
        return RunResult(
            script_name=script_name,
            status="EXCEPTION",
            return_code=1,
            duration_sec=int(time.time() - start_time),
            stdout_log=str(stdout_log),
            stderr_log=str(stderr_log),
            stderr_tail=str(e),
            error=str(e),
        )


def write_summary(results: List[RunResult], run_id: str):
    summary_path = LOGS_DIR / run_id / f"runs_summary_{run_id}.csv"

    with summary_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "script_name",
                "status",
                "return_code",
                "duration_sec",
                "stdout_log",
                "stderr_log",
                "error",
            ],
        )
        w.writeheader()

        for r in results:
            w.writerow({
                "script_name": r.script_name,
                "status": r.status,
                "return_code": r.return_code,
                "duration_sec": r.duration_sec,
                "stdout_log": r.stdout_log,
                "stderr_log": r.stderr_log,
                "error": r.error,
            })

    return summary_path


def main():
    print("\nValidando scripts...")

    scripts = [CATEGORIAS_DIR / s for s in SCRIPTS_TO_RUN]
    for s in scripts:
        if not s.exists():
            print(f"ERROR: No encontrado: {s}")
            sys.exit(1)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\nRun ID: {run_id}")
    print(f"Paralelismo: {MAX_WORKERS}\n")
    for s in scripts:
        print(" -", s.name)

    t0 = time.perf_counter()
    results: List[RunResult] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(run_one_script, s, run_id): s for s in scripts}

        for future in as_completed(futures):
            r = future.result()
            results.append(r)

            icon = "OK" if r.status == "OK" else "ERROR"
            print(f"\n[{icon}] {r.script_name} | {r.status} | {r.duration_sec}s | rc={r.return_code}")
            print("   stdout:", r.stdout_log)
            print("   stderr:", r.stderr_log)

            if r.status != "OK":
                print("   ---- tail stderr (ultimas 30 lineas) ----")
                print(r.stderr_tail or "(stderr vacio)")

    summary = write_summary(results, run_id)

    ok = sum(1 for r in results if r.status == "OK")
    bad = len(results) - ok

    elapsed = time.perf_counter() - t0
    hhmmss = time.strftime("%H:%M:%S", time.gmtime(elapsed))

    print("\n" + "=" * 60)
    print("🏁 EJECUCIÓN FINALIZADA")
    print(f"⏱️ Tiempo total: {elapsed:.1f}s ({hhmmss})")
    print(f"✅ OK: {ok} | ❌ errores: {bad}")
    print("📄 Resumen:", summary)
    print("=" * 60)

    sys.exit(0 if bad == 0 else 2)


if __name__ == "__main__":
    main()
