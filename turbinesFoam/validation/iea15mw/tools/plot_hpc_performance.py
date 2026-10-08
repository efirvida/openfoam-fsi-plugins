#!/usr/bin/env python
"""IEA 15 MW HPC performance results: scaling and decomposition methods.

Regenerates `analysis/hpc-performance.md` and the three figures from the CSVs the
studies write, so when the placement-dense curve lands the results update by
re-running this script instead of being edited by hand.

Sources (any of them may be missing while a study is still running):

    runs/iea15mw-scale-summary.csv          scaling, loose allocation
    runs/iea15mw-scale-summary-dense.csv    scaling, placement-controlled
    runs/iea15mw-decomp-summary.csv         decomposition methods

What the numbers mean, and what they do NOT:

- `step_s` is the median of the solver's own ExecutionTime deltas over a point of
  16 steps (0.1 revolution) on the medium D/48 mesh, so it is independent of the
  job's wall clock.
- `core_seconds = step_s * ranks` is the cost of one step; it is flat under perfect
  scaling and its first sharp rise is the knee. That is the reference-free way to
  read the curve -- the loose allocation's ABSOLUTE seconds carry a placement
  penalty (the same 192 tasks landed on 4 nodes one submission and on 21-33 in
  others), which is exactly what the dense curve isolates.
- `decompose_s` is read from decomposePar's own log line.

Usage:  python3 tools/plot_hpc_performance.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
ANALYSIS = ROOT / "analysis"
MD = ANALYSIS / "hpc-performance.md"

# The knee of the measured curve; drawn, not assumed.
KNEE = (72, 96)


def read(name: str) -> list[dict]:
    path = RUNS / name
    if not path.is_file():
        return []
    return [r for r in csv.DictReader(path.open())]


def scaling_rows(name: str) -> list[dict]:
    rows = read(name)
    out = []
    for r in rows:
        step = float(r["median_step_s"])
        ranks = int(r["ranks"])
        if not step or step != step:  # empty or NaN
            continue
        out.append(
            {
                "ranks": ranks,
                "cells_per_rank": int(r["cells_per_rank"]),
                "step_s": step,
                "core_seconds": step * ranks,
                "min_per_rev": step * 160 / 60,
                "h_4rev": step * 160 / 60 * 4 / 60,
                "wall_s": int(r["total_s"]),
            }
        )
    out.sort(key=lambda r: r["ranks"])
    return out


def method_rows() -> tuple[list[dict], list[int]]:
    rows = read("iea15mw-decomp-summary.csv")
    out = []
    densities = sorted({int(r["cells_per_rank"]) for r in rows}, reverse=True)
    for r in rows:
        out.append(
            {
                "method": r["method"],
                "ranks": int(r["ranks"]),
                "cells_per_rank": int(r["cells_per_rank"]),
                "step_s": float(r["median_step_s"]),
                "decompose_s": float(r["decompose_s"]) if r["decompose_s"] else None,
                "wall_s": int(r["total_s"]),
            }
        )
    return out, densities


def md_table(rows: list[dict], header: list[str], keys: list[str], fmt: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(f.format(r[k]) for k, f in zip(keys, fmt)) + " |")
    return "\n".join(lines) + "\n"


def plot_scaling(loose: list[dict], dense: list[dict]) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))

    for label, rows, style in (("suelta (lo que entrega la cola)", loose, "o-"),
                               ("densa (colocacion controlada)", dense, "s-")):
        if not rows:
            continue
        ax1.plot([r["cells_per_rank"] for r in rows], [r["step_s"] for r in rows],
                 style, label=label)
        ax2.plot([r["ranks"] for r in rows], [r["core_seconds"] for r in rows],
                 style, label=label)

    if loose:
        base = next((r for r in loose if r["ranks"] == 48), loose[0])
        ax1.plot([r["cells_per_rank"] for r in loose],
                 [base["step_s"] * base["ranks"] / r["ranks"] for r in loose],
                 "k--", lw=1, label="escalado ideal (1/N, anclado en 48)")

    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xlabel("celdas por core")
    ax1.set_ylabel("segundos por paso (mediana)")
    ax1.set_title("Costo por paso vs resolucion")
    ax1.grid(True, which="both", alpha=0.3)
    ax1.legend(fontsize=8)

    ax2.set_xscale("log")
    ax2.set_xlabel("rangos")
    ax2.set_ylabel("core-segundos por paso  (step_s x ranks)")
    ax2.set_title("Costo total: plano = escala perfecto")
    ax2.axvspan(*KNEE, color="tab:green", alpha=0.12, label=f"rodilla medida {KNEE[0]}-{KNEE[1]}")
    ax2.grid(True, which="both", alpha=0.3)
    ax2.legend(fontsize=8)

    fig.suptitle("IEA 15 MW ALM — escalado (malla medium D/48, 16 pasos por punto)", fontsize=10)
    fig.tight_layout()
    fig.savefig(ANALYSIS / "hpc-scaling.png", dpi=140)
    plt.close(fig)


def plot_methods(rows: list[dict], densities: list[int]) -> None:
    if not rows:
        return
    methods = ["scotch", "simple", "hierarchical"]
    colors = {"scotch": "tab:red", "simple": "tab:blue", "hierarchical": "tab:green"}
    width = 0.26
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))

    for i, m in enumerate(methods):
        xs, ys = [], []
        for j, d in enumerate(densities):
            r = next((r for r in rows if r["method"] == m and r["cells_per_rank"] == d), None)
            if r:
                xs.append(j + (i - 1) * width)
                ys.append(r["step_s"])
        ax1.bar(xs, ys, width, label=m, color=colors[m])

    ax1.set_xticks(range(len(densities)))
    ax1.set_xticklabels([f"{d // 1000}k\n({r} rangos)" for d, r in
                         zip(densities, [next((x['ranks'] for x in rows
                                               if x['cells_per_rank'] == d), 0)
                                         for d in densities])])
    ax1.set_ylabel("segundos por paso")
    ax1.set_title("Costo por paso: metodos")
    ax1.legend(fontsize=8)

    for i, m in enumerate(methods):
        xs, ys = [], []
        for j, d in enumerate(densities):
            r = next((r for r in rows if r["method"] == m and r["cells_per_rank"] == d), None)
            if r and r["decompose_s"]:
                xs.append(j + (i - 1) * width)
                ys.append(r["decompose_s"])
        ax2.bar(xs, ys, width, label=m, color=colors[m])

    ax2.set_xticks(range(len(densities)))
    ax2.set_xticklabels([f"{d // 1000}k" for d in densities])
    ax2.set_yscale("log")
    ax2.set_ylabel("segundos de decomposePar (log)")
    ax2.set_title("Costo de descomponer: scotch paga el grafo")
    ax2.legend(fontsize=8)

    fig.suptitle("IEA 15 MW ALM — metodos de particionado (malla medium, 0.1 rev)", fontsize=10)
    fig.tight_layout()
    fig.savefig(ANALYSIS / "hpc-methods.png", dpi=140)
    plt.close(fig)


def main() -> int:
    ANALYSIS.mkdir(exist_ok=True)
    loose = scaling_rows("iea15mw-scale-summary.csv")
    dense = scaling_rows("iea15mw-scale-summary-dense.csv")
    methods, densities = method_rows()

    plot_scaling(loose, dense)
    plot_methods(methods, densities)

    doc = ["# IEA 15 MW — rendimiento del HPC (escalado y particionado)\n",
           "Generado por `tools/plot_hpc_performance.py` desde los CSV de los estudios;",
           "re-ejecutarlo actualiza tablas y graficos (por ejemplo cuando entre la curva",
           "densa). **No editar a mano.**\n"]

    if loose or dense:
        doc.append("## Escalado\n")
        doc.append("Malla medium D/48 (6.508.528 celdas), 16 pasos por punto (0,1 rev),")
        doc.append("mediana de los deltas de `ExecutionTime`. `core-segundos` es el costo")
        doc.append("de un paso: plano = escalado perfecto.\n")
        if loose:
            doc.append("### Asignación suelta (sólo `--ntasks`: la coloca el planificador)\n")
            doc.append(md_table(
                loose,
                ["rangos", "celdas/core", "s/paso", "core-s/paso", "min/rev", "4 revs", "pared"],
                ["ranks", "cells_per_rank", "step_s", "core_seconds", "min_per_rev", "h_4rev", "wall_s"],
                ["{:,}", "{:,}", "{:.2f}", "{:.0f}", "{:.2f}", "{:.2f} h", "{} s"],
            ))
            doc.append("\nLos **absolutos** de esta curva están inflados por la colocación"
                       " dispersa; sirven para la forma, no para planificar tiempos.\n")
        if dense:
            doc.append("\n### Asignación densa (colocación controlada)\n")
            doc.append(md_table(
                dense,
                ["rangos", "celdas/core", "s/paso", "core-s/paso", "min/rev", "4 revs"],
                ["ranks", "cells_per_rank", "step_s", "core_seconds", "min_per_rev", "h_4rev"],
                ["{:,}", "{:,}", "{:.2f}", "{:.0f}", "{:.2f}", "{:.2f} h"],
            ))
        else:
            doc.append("\n> La curva densa todavía no corrió (`11610449` en cola): es la que"
                       " fija los absolutos.\n")
        doc.append(f"\n![escalado](hpc-scaling.png)\n")

    if methods:
        doc.append("\n## Métodos de particionado\n")
        doc.append("Mismos puntos (0,1 rev) con la misma asignación dentro de cada densidad,")
        doc.append("así que el **ratio** entre métodos es limpio aunque los absolutos no.\n")
        rows = []
        for d in densities:
            ref = next((r for r in methods if r["method"] == "scotch" and r["cells_per_rank"] == d), None)
            for m in ("scotch", "simple", "hierarchical"):
                r = next((r for r in methods if r["method"] == m and r["cells_per_rank"] == d), None)
                if not r:
                    continue
                rows.append({
                    "cells_per_rank": d,
                    "ranks": r["ranks"],
                    "method": m,
                    "step_s": r["step_s"],
                    "ratio": r["step_s"] / ref["step_s"] if ref else float("nan"),
                    "decompose_s": r["decompose_s"] if r["decompose_s"] else float("nan"),
                })
        doc.append(md_table(
            rows,
            ["celdas/core", "rangos", "método", "s/paso", "vs scotch", "decomposePar"],
            ["cells_per_rank", "ranks", "method", "step_s", "ratio", "decompose_s"],
            ["{:,}", "{}", "{}", "{:.2f}", "{:.2f}", "{:.1f} s"],
        ))
        doc.append("\n![metodos](hpc-methods.png)\n")

    doc.append("\n## Qué NO dicen estos números\n")
    doc.append("- La curva suelta mezcla la colocación con la resolución: cada slice puede")
    doc.append("  caer en nodos distintos (las mismas 192 tareas fueron a 4 nodos en una")
    doc.append("  asignación y a 21-33 en otras). Por eso existe la curva densa.")
    doc.append("- Los puntos de pocos rangos (36/24/12) salieron **no monótonos** (36 rangos")
    doc.append("  peor que 48 y que 24): ahí domina el ruido de colocación y no sirven para")
    doc.append("  decidir.")
    doc.append("- El horizonte de las corridas es 0,1 rev por punto: mide costo por paso, no")
    doc.append("  convergencia física.\n")

    MD.write_text("\n".join(doc), encoding="utf-8")

    print(f"escrito {MD.relative_to(ROOT)}")
    print(f"  escalado suelto: {len(loose)} puntos; denso: {len(dense)} puntos")
    print(f"  metodos: {len(methods)} pares en {len(densities)} densidades")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
