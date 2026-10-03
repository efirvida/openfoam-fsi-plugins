#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Three-model spanwise comparison for the IEA 15-240-RWT validation.

PLOT-ONLY, dependency-light script (matplotlib + csv + math + numpy only).  It
reads the per-element actuator outputs of the three live comparison runs that
share one mesh and one operating point and differ only in the force model:

* ALM      ``runs/iea15mw-asmcmp-alm/``
* ASM      ``runs/iea15mw-asmcmp-asm/``
* ASM-mesh ``runs/iea15mw-asmcmp-asm-mesh/``

Each run is averaged over its own last two rotor revolutions (the "same last-2
revolution rule", applied per run because the three runs are at different
transient depths).  The three curves are drawn against the embedded CCBlade
BEM reference at the same operating point, so the figure answers whether the
angle-of-attack offset and the tangential-load excess are a common *method*
effect or model-specific.  Writes ``runs/spanwise-3models.png`` and prints the
numeric table the figure is built from.

Panels (all share the ``r/R`` x axis)
-------------------------------------
1. ``alpha_deg``   local angle of attack            [deg]  + BEM offset per model
2. ``c_n``         normal / thrust coefficient      [-]    + ``model/BEM`` ratio
3. ``c_t``         tangential / torque coefficient  [-]    + ``model/BEM`` ratio
4. ``c_t/c_n``     torque-to-thrust ratio           [-]    (normalisation-free)

Column and unit conventions (verified against the ALM module CSV and reused
verbatim for all three runs, whose element headers are identical)
------------------------------------------------------------------
* ``root_dist`` is the blade-normalised span fraction in ``[0, 1]`` measured
  from the root cutout: ``r = HUB_RADIUS + root_dist * BLADE_SPAN`` and
  ``r/R = r / ROTOR_RADIUS`` (the convention baked into the embedded CCBlade
  ``r/R`` arrays, so the two are directly comparable).
* ``alpha_deg`` is the angle actually used for the polar lookup.
* ``c_ref_n``/``c_ref_t`` are the element normal/tangential *coefficients* in
  the flow (plane-of-rotation) reference frame:
  ``c_ref_n = cl*cos(phi) + cd*sin(phi)``,
  ``c_ref_t = cl*sin(phi) - cd*cos(phi)`` with ``phi`` the element inflow
  reference angle.  ``c_t/c_n`` is their ratio.

Derivation fallback (documented, but NOT needed for these three runs)
---------------------------------------------------------------------
A variant of this reader may meet per-element CSVs that carry the polar values
(``cl``, ``cd``, ``alpha_deg``) but omit ``c_ref_n``/``c_ref_t``.  In that case
the coefficients are reconstructed per row from the polar values and the local
blade geometry (``data/iea15mw_blade.csv``):

    theta = -pitch_deg          (pitch_deg interpolated at r, column of the
                                 blade CSV; collective pitch is 0)
    phi   = alpha_deg + theta   (inflow angle, degrees -> radians)
    c_n   = cl*cos(phi) + cd*sin(phi)
    c_t   = cl*sin(phi) - cd*cos(phi)

The fallback is applied per row and then averaged over the window.  All three
runs currently write ``c_ref_n``/``c_ref_t`` directly, so the fallback is
dormant; it is retained so the script stays correct if a force model stops
writing the coefficients.  (Cross-check at element 43 of the ALM run: the
fallback reproduces the written ``c_ref_n``/``c_ref_t`` to <= 3e-4.)

Blade-resolved references (digitized, PLOT-ONLY)
------------------------------------------------
The two published blade-resolved references overlaid on this figure are
VISUALLY DIGITIZED from rendered page images under ``/tmp/iea15mw_art/fig/``
(read-only), at roughly 15-27 stations per curve, with an estimated reading
uncertainty of +/-10 %.  No point is invented: straight segments between the
recorded stations are linear interpolations of points that were read.

1. de Oliveira et al., OMAE2023-105084, FIGURE 6 (``omae_p8.png``):
   "R15Mesh-1 ... mean distributed forces along the blade span, benchmarked
   against the OpenFAST results", panels (a) Normal force and (b) Tangential
   force, x axis ``Radius [m]`` (0-120), so ``r/R = radius/120.67532``.
   Condition: V = 10 m/s uniform, rotor-only, 35.4M cells, y+ 60-350, first
   cell 1 mm (a blade-resolved URANS with walls and a boundary layer).  Curves
   read: ``R15Mesh-1 URANS CFL=2`` (green triangles) and ``OpenFAST - AeroDyn
   v15`` (grey solid).  The CFL=1 and CFL=4 curves are NOT read (the authors
   recommend CFL=2; CFL=4 is not temporally converged).

2. Yi et al., Applied Ocean Research (2026) 104935, Fig. 13 (``yi_p11.png``):
   "(a) Normal force per unit length, Fn; (b) Torque per unit length, Q"
   versus ``r/R`` for ``ws=8m/s`` and ``ws=9m/s``.  The 9 m/s pair is read:
   ``ws=9m/s-Present`` (their blade-resolved URANS, dashed) and
   ``ws=9m/s-BEMT`` (open circles).  The 8 m/s pair is a different wind speed
   and is NOT read here.

UNITS.  de Oliveira's y axis is labelled ``[kN]`` but the values (0-12 over a
~120 m blade) are per unit span, i.e. kN/m -- the same quantity as CCBlade's
Np/Tp in N/m and the ALM ``f_ref_n/dr``.  Yi's ``Fn`` is explicitly kN/m and
``Q`` is a torque per unit length (kN.m/m), so the tangential force per unit
length is ``Q/r``.  All reference forces are therefore treated as per unit
length.

NORMALISATION.  Both references run at a different wind speed than our point
(V = 10.659 m/s).  Their forces are rescaled by the dynamic-pressure ratio
``(V_RATED/V_ref)**2`` (de Oliveira 10 m/s -> x1.136; Yi 9 m/s -> x1.402) so
the levels are directly comparable to ours.

COEFFICIENTS.  To enter the ``c_n``/``c_t`` panels the reference forces are
converted with the local relative dynamic pressure and the blade chord from
``data/iea15mw_blade.csv``::

    W(r) = sqrt(V_RATED**2 + (Omega*r)**2),   Omega = RPM_RATED*2*pi/60
    c_n  = f_n / (0.5*rho*W**2 * chord(r))
    c_t  = f_t / (0.5*rho*W**2 * chord(r)),   f_t = Q/r  (Yi only)

with ``r = (r/R)*ROTOR_RADIUS`` and ``chord(r)`` linearly interpolated on the
``r_over_R`` column of the blade geometry.  This is an approximate but
self-consistent conversion (the references report section forces), so the
resulting coefficients are directly comparable to the model
``c_ref_n``/``c_ref_t``.

CCBlade BEM reference (embedded, reproducible)
----------------------------------------------
The BEM arrays below were produced once from the maintainer's Aeroelast, from
``/scratch/leahk/eduardo.donestevez/fem-shell``::

    LD_LIBRARY_PATH=/scratch/app/gcc/14.2.0/lib64:$LD_LIBRARY_PATH PYTHONPATH=src \
      /scratch/leahk/eduardo.donestevez/venv/bin/python - <<'EOF'
    from aeroelast.models.blade.aerodynamics import load_blade_aero
    from aeroelast.solvers.bem.engine import BEMSolver
    ba = load_blade_aero("tests/IEA-15-240-RWT.yaml", hub_radius=3.97, n_blades=3)
    s  = BEMSolver(ba, rho=1.225, precone=4.0, tilt=0.0, yaw=0.0,
                   hub_height=150.0, shear_exp=0.0)
    res = s.compute(10.659, 7.518, 0.0, 0.0)
    EOF

which returned ``CP = 0.49098`` / ``CT = 0.79341`` (self-check 0.4910 / 0.7934).
The arrays are embedded verbatim so this figure needs no Aeroelast import.

Usage:
    plot_3models_spanwise.py [--revs N] [--rpm R] [--out FILE]
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
RUNS_DIR = ROOT / "runs"
BLADE_CSV = ROOT / "data" / "iea15mw_blade.csv"
DEFAULT_OUT = RUNS_DIR / "spanwise-3models.png"
REFERENCES_OUT = RUNS_DIR / "spanwise-references.png"

ELEMENT_DIR = Path("postProcessing") / "actuatorLineElements" / "0"
TURBINE_CSV = Path("postProcessing") / "turbines" / "0" / "turbine.csv"

#: Rated point of the IEA 15-240-RWT case (matches system/fvOptions.ALM).
RHO = 1.225
V_RATED = 10.659
RPM_RATED = 7.518
ROTOR_RADIUS = 120.67532
HUB_RADIUS = 3.97
BLADE_SPAN = 117.0
N_BLADES = 3
PRECONE_DEG = 4.0
TSR_RATED = 8.913

#: Default averaging window: the last two rotor revolutions of each run.
DEFAULT_REVS = 2.0

#: Span window used for the headline offset/excess annotations.
ANNOTATE_LO = 0.30
ANNOTATE_HI = 0.90

#: Common stations printed in the terminal table.
STATIONS = (0.30, 0.45, 0.60, 0.75, 0.90)

#: The three force models under comparison: (label, run directory, colour, marker).
MODELS = (
    ("ALM", RUNS_DIR / "iea15mw-asmcmp-alm", "tab:blue", "o"),
    ("ASM", RUNS_DIR / "iea15mw-asmcmp-asm", "tab:green", "^"),
    ("ASM-mesh", RUNS_DIR / "iea15mw-asmcmp-asm-mesh", "tab:orange", "s"),
)
BEM_COLOR = "0.15"
RATIO_COLOR = "0.45"

# --- CCBlade BEM reference (embedded) ------------------------------------
#: BEM stations as r/R (r in metres / ROTOR_RADIUS).
BEM_RR = (
    0.0328982, 0.0526848, 0.0724714, 0.092258, 0.112045, 0.131831, 0.151618,
    0.171404, 0.191191, 0.210978, 0.230764, 0.250551, 0.270337, 0.290124,
    0.309911, 0.329697, 0.349484, 0.369271, 0.389057, 0.408844, 0.42863,
    0.448417, 0.468204, 0.48799, 0.507777, 0.527563, 0.54735, 0.567137,
    0.586923, 0.60671, 0.626496, 0.646283, 0.66607, 0.685856, 0.705643,
    0.725429, 0.745216, 0.765003, 0.784789, 0.804576, 0.824362, 0.844149,
    0.863936, 0.883722, 0.903509, 0.923295, 0.943082, 0.962869, 0.982655,
    0.987899, 0.992746, 0.997594, 1.00244,
)
BEM_ALPHA_DEG = (
    53.6152, 49.2572, 41.7282, 35.6201, 30.7792, 19.8734, 16.7894, 14.5679,
    12.9387, 11.7059, 9.7053, 8.96115, 8.37663, 7.95477, 7.64776, 7.59426,
    7.41665, 7.25693, 7.10425, 7.16898, 7.02982, 6.91026, 6.80774, 6.71904,
    6.82122, 6.75477, 6.69806, 6.64594, 6.59804, 6.554, 6.5192, 6.49632,
    6.48831, 6.50127, 6.54112, 6.74763, 6.86167, 6.98679, 7.10874, 7.21126,
    7.28075, 7.26879, 7.20829, 7.11455, 6.97915, 6.78887, 6.51595, 6.09108,
    5.29659, 4.98498, 4.69045, 4.46822, 4.92292,
)
BEM_CN = (
    0.327246, 0.316849, 0.294051, 0.270399, 0.24772, 1.5004, 1.57632,
    1.59766, 1.58402, 1.55178, 1.63061, 1.57307, 1.52185, 1.48276, 1.45351,
    1.4059, 1.38735, 1.37028, 1.3535, 1.30207, 1.28617, 1.27245, 1.26066,
    1.25045, 1.21041, 1.20299, 1.1967, 1.19088, 1.18552, 1.18074, 1.17717,
    1.17495, 1.17446, 1.17642, 1.18156, 1.16034, 1.1744, 1.1898, 1.20481,
    1.21744, 1.22605, 1.22477, 1.2176, 1.20643, 1.19027, 1.16758, 1.13517,
    1.08528, 0.994517, 0.959689, 0.927063, 0.902588, 0.952628,
)
BEM_CT = (
    -0.124138, -0.148684, -0.189827, -0.222226, -0.247254, 0.804273,
    0.749865, 0.666203, 0.579763, 0.501322, 0.516641, 0.455167, 0.405259,
    0.365366, 0.333139, 0.307265, 0.284621, 0.264545, 0.246397, 0.231568,
    0.216999, 0.204116, 0.192659, 0.182401, 0.171932, 0.163633, 0.156077,
    0.149147, 0.142788, 0.138133, 0.132829, 0.128002, 0.123634, 0.119702,
    0.116185, 0.114201, 0.111359, 0.108721, 0.106266, 0.103989, 0.101872,
    0.0998347, 0.0977025, 0.0952526, 0.0922342, 0.0882905, 0.0827887,
    0.0742553, 0.057719, 0.0515146, 0.0459012, 0.0420918, 0.0533293,
)
#: CCBlade self-check at the operating point (must be CP 0.4910 / CT 0.7934).
BEM_CP = 0.49098
BEM_CT_ROTOR = 0.79341

#: Shaft speed implied by the rated TSR (rad/s), used for the reference dynamic
#: pressure W(r) = sqrt(V**2 + (Omega r)**2).
OMEGA_RATED = RPM_RATED * 2.0 * math.pi / 60.0

# --- Digitized blade-resolved references ---------------------------------
# All arrays below are VISUALLY DIGITIZED from the published figures (see the
# module docstring for the panels, the case and the +/-10 % reading
# uncertainty).  Forces are per unit span in kN/m (tangential force for Yi).
# ``*_RADIUS`` values are read straight off the reference x axes (metres or
# r/R); ``*_FORCE`` are the matching y values.  No invented points.

#: Dynamic-pressure rescaling to our rated speed.  de Oliveira runs at 10 m/s,
#: Yi at 9 m/s; ours is V_RATED = 10.659 m/s.
REF_RESCALE_DEOLIV = (V_RATED / 10.0) ** 2  # = 1.136
REF_RESCALE_YI = (V_RATED / 9.0) ** 2  # = 1.402

# de Oliveira et al. (OMAE2023-105084), FIGURE 6(a): normal force [kN/m],
# Radius [m]; R15Mesh-1 URANS CFL=2 (green) and OpenFAST-AeroDyn v15 (grey).
DEOLIV_CN_CFL2_R_M = (
    4.3, 8.6, 13.0, 17.3, 21.6, 25.9, 30.3, 34.6, 38.9, 43.2, 47.6, 51.9,
    56.2, 60.5, 64.9, 73.5, 77.8, 82.2, 86.5, 90.8, 95.1, 99.5, 103.8,
    108.1, 112.4, 116.8,
)
DEOLIV_CN_CFL2 = (
    0.54, 0.84, 0.69, 1.25, 1.82, 2.15, 2.66, 3.07, 3.45, 3.91, 4.17, 4.41,
    4.60, 5.28, 6.27, 7.46, 8.06, 8.48, 9.10, 9.85, 10.33, 10.33, 10.03,
    9.70, 8.75, 6.99,
)
DEOLIV_CN_FAST_R_M = (
    5.9, 10.3, 14.6, 18.9, 23.2, 27.6, 31.9, 36.2, 40.5, 44.9, 49.2, 53.5,
    57.8, 62.2, 66.5, 70.8, 75.1, 79.5, 83.8, 88.1, 92.4, 96.8, 101.1,
    105.4, 109.7, 114.1,
)
DEOLIV_CN_FAST = (
    0.18, 0.48, 1.25, 1.94, 2.66, 3.28, 3.85, 4.33, 4.84, 5.34, 5.82, 6.30,
    6.78, 7.25, 7.73, 8.21, 8.69, 9.16, 9.64, 10.21, 10.78, 11.13, 11.16,
    10.90, 10.24, 8.75,
)

# de Oliveira et al. (OMAE2023-105084), FIGURE 6(b): tangential force [kN/m],
# Radius [m]; same two curves.
DEOLIV_CT_CFL2_R_M = (
    4.4, 8.8, 13.3, 17.7, 22.1, 26.5, 31.0, 35.4, 39.8, 44.2, 48.7, 53.1,
    57.5, 61.9, 66.4, 70.8, 75.2, 79.6, 84.1, 88.5, 92.9, 97.3, 101.8,
    106.2, 110.6, 115.0,
)
DEOLIV_CT_CFL2 = (
    0.306, 0.446, 0.408, 0.657, 0.739, 0.749, 0.767, 0.749, 0.780, 0.753,
    0.712, 0.722, 0.691, 0.722, 0.811, 0.818, 0.852, 0.835, 0.828, 0.775,
    0.701, 0.597, 0.534, 0.470, 0.390, 0.145,
)
DEOLIV_CT_FAST_R_M = (
    1.7, 6.1, 10.5, 14.9, 19.4, 23.8, 28.2, 32.6, 37.1, 41.5, 45.9, 50.3,
    54.7, 59.2, 63.6, 68.0, 72.4, 76.9, 81.3, 85.7, 90.1, 94.6, 99.0,
    103.4, 107.8, 112.3, 116.7,
)
DEOLIV_CT_FAST = (
    -0.025, -0.012, 0.268, 0.640, 0.794, 0.903, 0.954, 0.961, 0.965,
    0.965, 0.961, 0.961, 0.958, 0.951, 0.947, 0.941, 0.941, 0.937, 0.941,
    0.941, 0.934, 0.927, 0.906, 0.869, 0.794, 0.640, 0.036,
)

# Yi et al. (2026), Fig. 13, the ws = 9 m/s pair.  Panel (a) Fn [kN/m],
# panel (b) Q [kN.m/m] (torque per unit length -> f_t = Q/r).
YI_FN_PRESENT_RR = (
    0.119, 0.163, 0.202, 0.222, 0.241, 0.261, 0.418, 0.438, 0.457, 0.477,
    0.496, 0.536, 0.555, 0.575, 0.594, 0.614, 0.634, 0.653, 0.673, 0.692,
    0.712, 0.732, 0.751, 0.771, 0.830, 0.869, 0.888, 0.908, 0.928, 0.947,
)
YI_FN_PRESENT = (
    0.70, 0.85, 1.03, 1.28, 1.51, 1.76, 3.81, 4.05, 4.28, 4.50, 4.69,
    5.14, 5.40, 5.61, 5.83, 6.04, 6.26, 6.49, 6.74, 7.01, 7.27, 7.52,
    7.79, 8.02, 8.26, 8.11, 7.90, 7.46, 6.80, 5.38,
)
YI_FN_BEMT_RR = (
    0.119, 0.156, 0.190, 0.234, 0.268, 0.305, 0.340, 0.377, 0.420, 0.452,
    0.494, 0.530, 0.565, 0.600, 0.638, 0.675, 0.712, 0.749, 0.788, 0.825,
    0.860, 0.900, 0.933,
)
YI_FN_BEMT = (
    0.22, 1.01, 1.59, 2.16, 2.69, 3.15, 3.57, 3.99, 4.41, 4.82, 5.23,
    5.66, 6.08, 6.48, 6.91, 7.32, 7.77, 8.28, 8.75, 9.00, 8.94, 8.58,
    7.80,
)
YI_Q_PRESENT_RR = (
    0.209, 0.234, 0.259, 0.284, 0.309, 0.384, 0.409, 0.434, 0.459, 0.484,
    0.509, 0.534, 0.559, 0.708, 0.733, 0.758, 0.783, 0.808, 0.833, 0.858,
    0.883, 0.908, 0.933,
)
YI_Q_PRESENT = (
    11.0, 13.3, 16.1, 19.6, 22.4, 30.6, 32.7, 35.1, 37.5, 39.4, 41.8,
    44.1, 46.3, 59.6, 61.6, 62.5, 63.3, 63.3, 64.1, 63.9, 61.8, 56.7,
    44.5,
)
YI_Q_BEMT_RR = (
    0.122, 0.160, 0.237, 0.267, 0.305, 0.340, 0.378, 0.415, 0.452, 0.490,
    0.526, 0.568, 0.600, 0.640, 0.665, 0.680, 0.710, 0.733, 0.758, 0.783,
    0.808, 0.833, 0.858, 0.883, 0.908, 0.933,
)
YI_Q_BEMT = (
    -0.2, 3.3, 8.0, 10.7, 13.1, 15.9, 19.3, 23.0, 26.9, 31.3, 36.3, 41.5,
    47.7, 53.3, 57.0, 60.5, 70.0, 75.9, 83.8, 94.9, 100.4, 103.7, 105.5,
    103.1, 99.0, 84.0,
)

#: Reference style: (label, colour, linestyle, marker).
REF_STYLES = {
    "deoliv_cfl2": ("de Oliveira 10 m/s CFL=2 (rescaled)", "firebrick", "-", "v"),
    "deoliv_fast": ("de Oliveira OpenFAST (rescaled)", "0.35", "-", None),
    "yi_present": ("Yi 9 m/s Present URANS (rescaled)", "saddlebrown", "--", None),
    "yi_bemt": ("Yi 9 m/s BEMT (rescaled)", "mediumpurple", "-.", "o"),
}

#: Element CSV columns that must be present for each reading mode.
DIRECT_POLARS = ("time", "root_dist", "alpha_deg", "c_ref_n", "c_ref_t")
DERIVED_POLARS = ("time", "root_dist", "alpha_deg", "cl", "cd")


# --- geometry helper ------------------------------------------------------
def load_pitch_table(path: Path):
    """Return ``(radii, pitch_deg)`` from ``data/iea15mw_blade.csv``.

    The blade CSV starts with ``#`` comment lines and has a
    ``radius_m,pitch_deg`` pair per station.  Used only by the derivation
    fallback.
    """
    radii: list[float] = []
    pitch: list[float] = []
    if not path.is_file():
        return radii, pitch
    with path.open(encoding="utf-8", newline="") as stream:
        lines = [line for line in stream if not line.startswith("#")]
    reader = csv.DictReader(lines)
    for row in reader:
        try:
            radii.append(float(row["radius_m"]))
            pitch.append(float(row["pitch_deg"]))
        except (TypeError, ValueError, KeyError):
            continue
    return radii, pitch


def pitch_at(radii, pitch, radius: float) -> float:
    """Linear interpolation of ``pitch_deg`` at ``radius`` [m].

    ``numpy.interp`` clamps outside the table to the end values, which is the
    desired behaviour for this fallback.
    """
    if not radii:
        return 0.0
    return float(np.interp(radius, radii, pitch))


# --- digitized-reference helpers ------------------------------------------
def load_chord_table(path: Path):
    """Return ``(r_over_R, chord_m)`` from ``data/iea15mw_blade.csv``.

    Used to convert the digitized reference forces (per unit span) into
    section coefficients with the same geometry the models use.
    """
    rr: list[float] = []
    chord: list[float] = []
    if not path.is_file():
        return np.array(rr), np.array(chord)
    with path.open(encoding="utf-8", newline="") as stream:
        lines = [line for line in stream if not line.startswith("#")]
    reader = csv.DictReader(lines)
    for row in reader:
        try:
            rr.append(float(row["r_over_R"]))
            chord.append(float(row["chord_m"]))
        except (TypeError, ValueError, KeyError):
            continue
    return np.array(rr), np.array(chord)


def reference_coefficients(rr, force_kN_per_m, rescale, chord_table,
                           torque: bool = False):
    """Convert a digitized per-span force into a section coefficient.

    ``force_kN_per_m`` is in kN per metre of span.  ``torque=True`` means the
    digitized quantity is a torque per unit length (kN.m/m, Yi's ``Q``) and is
    divided by the radius to obtain the tangential force.  ``rescale`` is the
    dynamic-pressure ratio ``(V_RATED/V_ref)**2``.  ``chord_table`` is
    ``(r_over_R, chord_m)``.  The local relative dynamic pressure is
    ``0.5*rho*(V_RATED**2 + (Omega*r)**2)``.
    """
    rr = np.asarray(rr, dtype=float)
    force = np.asarray(force_kN_per_m, dtype=float) * rescale
    radius = rr * ROTOR_RADIUS
    w = np.sqrt(V_RATED * V_RATED + (OMEGA_RATED * radius) ** 2)
    q = 0.5 * RHO * w * w
    chord = np.interp(rr, chord_table[0], chord_table[1])
    force_span = force * 1000.0  # kN/m -> N/m
    if torque:
        with np.errstate(divide="ignore", invalid="ignore"):
            force_span = force_span / radius
    return force_span / (q * chord)


def reference_series(chord_table) -> list[dict]:
    """The four digitized references as coefficient series.

    Each entry is a dict with ``key``, ``label``, ``color``, ``ls``, ``marker``
    and the ``rr_cn``/``cn`` and ``rr_ct``/``ct`` arrays (the normal and
    tangential digitizations live on different span grids).
    """
    out = []

    def add(key, rr_cn, force_cn, rr_ct, force_ct, rescale, ct_torque):
        label, color, ls, marker = REF_STYLES[key]
        out.append({
            "key": key,
            "label": label,
            "color": color,
            "ls": ls,
            "marker": marker,
            "rr_cn": np.asarray(rr_cn, dtype=float),
            "cn": reference_coefficients(
                rr_cn, force_cn, rescale, chord_table),
            "rr_ct": np.asarray(rr_ct, dtype=float),
            "ct": reference_coefficients(
                rr_ct, force_ct, rescale, chord_table, torque=ct_torque),
        })

    # de Oliveira reports a tangential force per unit span (kN/m): ct_torque
    # is False.  Yi reports a torque per unit length Q (kN.m/m): divide by r.
    add(
        "deoliv_cfl2",
        np.asarray(DEOLIV_CN_CFL2_R_M) / ROTOR_RADIUS, DEOLIV_CN_CFL2,
        np.asarray(DEOLIV_CT_CFL2_R_M) / ROTOR_RADIUS, DEOLIV_CT_CFL2,
        REF_RESCALE_DEOLIV, False,
    )
    add(
        "deoliv_fast",
        np.asarray(DEOLIV_CN_FAST_R_M) / ROTOR_RADIUS, DEOLIV_CN_FAST,
        np.asarray(DEOLIV_CT_FAST_R_M) / ROTOR_RADIUS, DEOLIV_CT_FAST,
        REF_RESCALE_DEOLIV, False,
    )
    add(
        "yi_present", YI_FN_PRESENT_RR, YI_FN_PRESENT,
        YI_Q_PRESENT_RR, YI_Q_PRESENT, REF_RESCALE_YI, True,
    )
    add(
        "yi_bemt", YI_FN_BEMT_RR, YI_FN_BEMT,
        YI_Q_BEMT_RR, YI_Q_BEMT, REF_RESCALE_YI, True,
    )
    return out


# --- live-run reader (same conventions as compare_spanwise.py) -------------
def _element_index(path: Path) -> int:
    """Element number of ``turbine.blade1.element<N>.csv``."""
    stem = path.name
    marker = ".element"
    start = stem.rfind(marker)
    if start < 0:
        raise ValueError(f"{path}: not an element CSV")
    return int(stem[start + len(marker) : stem.rfind(".")])


def _header(path: Path):
    """Column names of the first line of ``path``."""
    with path.open(encoding="utf-8", newline="") as stream:
        return [name.strip() for name in stream.readline().split(",")]


def _last_time(path: Path) -> float | None:
    """Last ``time`` value in a CSV, skipping blank/truncated rows."""
    if not path.is_file():
        return None
    value = None
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            if row is None:
                continue
            try:
                value = float(row["time"])
            except (TypeError, ValueError):
                continue
    return value


def window_bounds(turbine_csv: Path, revs: float, rpm: float):
    """Averaging window ``[t_start, t_end]`` and the rotor period."""
    t_end = _last_time(turbine_csv)
    if t_end is None:
        raise FileNotFoundError(
            f"{turbine_csv}: no time rows; cannot bound the averaging window"
        )
    period = 60.0 / rpm
    return t_end - revs * period, t_end, period


def average_element(path: Path, t_start: float, t_end: float, mode: str,
                    pitch_table) -> tuple[float, float, float, float] | None:
    """Window mean ``(root_dist, alpha_deg, c_n, c_t)`` for one element CSV.

    ``mode`` is ``"direct"`` when the file carries ``c_ref_n``/``c_ref_t``, or
    ``"derived"`` when they must be reconstructed from ``cl``/``cd`` and the
    blade twist (see module docstring).  Returns ``None`` when the window
    holds no sample for this element.
    """
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if header is None:
            return None
        index = {name.strip(): i for i, name in enumerate(header)}
        i_time = index.get("time")
        i_alpha = index.get("alpha_deg")
        i_root = index.get("root_dist")
        if i_time is None or i_alpha is None or i_root is None:
            return None
        if mode == "direct":
            i_cn = index.get("c_ref_n")
            i_ct = index.get("c_ref_t")
            if i_cn is None or i_ct is None:
                return None
            return _average_direct(
                reader, t_start, t_end, i_time, i_alpha, i_root, i_cn, i_ct
            )
        i_cl = index.get("cl")
        i_cd = index.get("cd")
        if i_cl is None or i_cd is None:
            return None
        return _average_derived(
            reader, t_start, t_end, i_time, i_alpha, i_root, i_cl, i_cd,
            pitch_table,
        )


def _average_direct(reader, t_start, t_end, i_time, i_alpha, i_root, i_cn,
                    i_ct):
    """Window mean of the coefficients written directly by the run."""
    root_sum = alpha_sum = cn_sum = ct_sum = 0.0
    count = 0
    for row in reader:
        if not row:
            continue
        try:
            time = float(row[i_time])
            if time < t_start or time > t_end:
                continue
            root_sum += float(row[i_root])
            alpha_sum += float(row[i_alpha])
            cn_sum += float(row[i_cn])
            ct_sum += float(row[i_ct])
        except (ValueError, IndexError):
            continue
        count += 1
    if count == 0:
        return None
    return (root_sum / count, alpha_sum / count, cn_sum / count,
            ct_sum / count)


def _average_derived(reader, t_start, t_end, i_time, i_alpha, i_root, i_cl,
                     i_cd, pitch_table):
    """Window mean with ``c_n``/``c_t`` reconstructed from ``cl``/``cd``."""
    root_sum = alpha_sum = cn_sum = ct_sum = 0.0
    count = 0
    for row in reader:
        if not row:
            continue
        try:
            time = float(row[i_time])
            if time < t_start or time > t_end:
                continue
            root = float(row[i_root])
            alpha = float(row[i_alpha])
            radius = HUB_RADIUS + root * BLADE_SPAN
            pitch = pitch_at(pitch_table[0], pitch_table[1], radius)
            phi = math.radians(alpha - pitch)
            cl = float(row[i_cl])
            cd = float(row[i_cd])
            cn = cl * math.cos(phi) + cd * math.sin(phi)
            ct = cl * math.sin(phi) - cd * math.cos(phi)
        except (ValueError, IndexError):
            continue
        root_sum += root
        alpha_sum += alpha
        cn_sum += cn
        ct_sum += ct
        count += 1
    if count == 0:
        return None
    return (root_sum / count, alpha_sum / count, cn_sum / count,
            ct_sum / count)


def load_profile(label: str, run_dir: Path, revs: float, rpm: float) -> dict:
    """Averaged spanwise profile of one run, as a dict of ``numpy`` arrays."""
    element_dir = run_dir / ELEMENT_DIR
    turbine_csv = run_dir / TURBINE_CSV
    if not element_dir.is_dir():
        raise FileNotFoundError(f"{element_dir}: not a directory")
    files = sorted(element_dir.glob("*.csv"), key=_element_index)
    if not files:
        raise FileNotFoundError(f"{element_dir}: no element CSVs")
    header = _header(files[0])
    mode = "direct" if {"c_ref_n", "c_ref_t"} <= set(header) else "derived"
    pitch_table = load_pitch_table(BLADE_CSV) if mode == "derived" else ([], [])

    t_start, t_end, period = window_bounds(turbine_csv, revs, rpm)

    rr, alpha, cn, ct = [], [], [], []
    missing = []
    for path in files:
        element = average_element(path, t_start, t_end, mode, pitch_table)
        if element is None:
            missing.append(_element_index(path))
            continue
        rr.append((HUB_RADIUS + element[0] * BLADE_SPAN) / ROTOR_RADIUS)
        alpha.append(element[1])
        cn.append(element[2])
        ct.append(element[3])
    rr = np.array(rr)
    alpha = np.array(alpha)
    cn = np.array(cn)
    ct = np.array(ct)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(cn != 0.0, ct / cn, np.nan)
    return {
        "label": label,
        "run_dir": run_dir,
        "element_dir": element_dir,
        "turbine_csv": turbine_csv,
        "header": header,
        "mode": mode,
        "n_files": len(files),
        "n_used": len(alpha),
        "missing": missing,
        "rr": rr,
        "alpha": alpha,
        "cn": cn,
        "ct": ct,
        "ratio": ratio,
        "window": (t_start, t_end, period),
        "revs_to_end": t_end / period,
    }


# --- table and summarise ---------------------------------------------------
def bem_at(value, rr):
    """Interpolate an embedded BEM array at ``rr``."""
    return np.interp(rr, BEM_RR, value)


def print_model_report(profiles) -> None:
    """Per-model window, input paths, file counts and header line."""
    print("=" * 78)
    print("INPUTS (read-only; all runs are live and were not modified)")
    print("=" * 78)
    for profile in profiles:
        t_start, t_end, period = profile["window"]
        print(f"\n[{profile['label']}]")
        print(f"  element dir : {profile['element_dir']}")
        print(f"  turbine csv : {profile['turbine_csv']}")
        print(f"  element files found : {profile['n_files']} "
              f"(used {profile['n_used']}"
              + (f", no in-window samples for {profile['missing']}"
                 if profile["missing"] else "") + ")")
        print(f"  mode        : {profile['mode']} "
              + ("(c_ref_n/c_ref_t written by the run)"
                 if profile["mode"] == "direct"
                 else "(reconstructed from cl/cd + blade pitch)"))
        print(f"  header      : {','.join(profile['header'])}")
        print(f"  window      : t_start {t_start:.6f} s   "
              f"t_end {t_end:.6f} s   "
              f"({(t_end - t_start) / period:.3f} revs averaged, "
              f"period {period:.6f} s)")
        print(f"  run to date : {profile['revs_to_end']:.3f} revs "
              f"(t_end/period at {RPM_RATED} rpm)")


def print_station_table(profiles) -> None:
    """Compact model-vs-BEM table at :data:`STATIONS`."""
    print("\n" + "=" * 78)
    print("COMMON-STATION TABLE  (model vs CCBlade BEM, BEM interpolated)")
    print("=" * 78)
    header = ("r/R", "model", "alpha_deg", "c_n", "c_t",
              "c_n/BEM", "c_t/BEM")
    print("  " + "  ".join(f"{name:>8}" for name in header))
    model_lookup = {p["label"]: p for p in profiles}
    for station in STATIONS:
        bem_alpha = float(bem_at(BEM_ALPHA_DEG, station))
        bem_cn = float(bem_at(BEM_CN, station))
        bem_ct = float(bem_at(BEM_CT, station))
        rows = [("BEM", bem_alpha, bem_cn, bem_ct, 1.0, 1.0)]
        for label, _, _, _ in MODELS:
            profile = model_lookup.get(label)
            if profile is None:
                rows.append((label, *_nan_fields()))
                continue
            a = float(np.interp(station, profile["rr"], profile["alpha"]))
            n = float(np.interp(station, profile["rr"], profile["cn"]))
            t = float(np.interp(station, profile["rr"], profile["ct"]))
            rows.append((label, a, n, t, n / bem_cn, t / bem_ct))
        for label, a, n, t, rn, rt in rows:
            print(
                "  "
                + "  ".join(
                    (
                        f"{station:>8.3f}", f"{label:>8}", f"{a:>8.3f}",
                        f"{n:>8.4f}", f"{t:>8.4f}", f"{rn:>8.3f}",
                        f"{rt:>8.3f}",
                    )
                )
            )
        print()


def _nan_fields():
    nan = float("nan")
    return nan, nan, nan, nan, nan


def print_offsets(profiles) -> None:
    """Mean BEM offset per model over the annotation span."""
    print("=" * 78)
    print(f"SPAN-WINDOW MEANS over r/R in [{ANNOTATE_LO:g}, {ANNOTATE_HI:g}]")
    print("=" * 78)
    for profile in profiles:
        rr = profile["rr"]
        mask = (rr >= ANNOTATE_LO) & (rr <= ANNOTATE_HI)
        d_alpha = profile["alpha"][mask] - bem_at(BEM_ALPHA_DEG, rr)[mask]
        excess_n = (profile["cn"][mask] / bem_at(BEM_CN, rr)[mask] - 1.0) * 100.0
        excess_t = (profile["ct"][mask] / bem_at(BEM_CT, rr)[mask] - 1.0) * 100.0
        print(
            f"  {profile['label']:>8}: "
            f"mean d_alpha {d_alpha.mean():+.3f} deg "
            f"(min {d_alpha.min():+.3f}, max {d_alpha.max():+.3f})   "
            f"c_n excess {excess_n.mean():+.1f} %   "
            f"c_t excess {excess_t.mean():+.1f} %"
        )


# --- figure ---------------------------------------------------------------
def _print_digitized(name, panel, unit, rr, values) -> None:
    """Print one digitized reference curve as paste-ready arrays."""
    print(f"\n  [{name}]")
    print(f"    panel   : {panel}")
    print(f"    units   : {unit}   (VISUALLY DIGITIZED, +/-10 %)")
    print("    r/R : " + ", ".join(f"{v:.4f}" for v in rr))
    print("    val : " + ", ".join(f"{v:g}" for v in values))


def print_digitized_tables() -> None:
    """Print the raw digitized reference arrays, marked as digitized."""
    print("\n" + "=" * 78)
    print("DIGITIZED BLADE-RESOLVED REFERENCES  (visually read, +/-10 %)")
    print("=" * 78)
    print("  Both references are rescaled to our V = "
          f"{V_RATED:g} m/s by the dynamic-pressure ratio:")
    print(f"    de Oliveira (10 m/s) x{REF_RESCALE_DEOLIV:.4f}   "
          f"Yi (9 m/s) x{REF_RESCALE_YI:.4f}")
    _print_digitized(
        "de Oliveira OMAE2023-105084 Fig.6(a) Normal force, R15Mesh-1 CFL=2",
        "Fig.6(a) Normal force [kN/m], R15Mesh-1 URANS CFL=2, V=10 m/s",
        "kN/m", np.asarray(DEOLIV_CN_CFL2_R_M) / ROTOR_RADIUS, DEOLIV_CN_CFL2,
    )
    _print_digitized(
        "de Oliveira OMAE2023-105084 Fig.6(a) Normal force, OpenFAST",
        "Fig.6(a) Normal force [kN/m], OpenFAST-AeroDyn v15, V=10 m/s",
        "kN/m", np.asarray(DEOLIV_CN_FAST_R_M) / ROTOR_RADIUS, DEOLIV_CN_FAST,
    )
    _print_digitized(
        "de Oliveira OMAE2023-105084 Fig.6(b) Tangential force, R15Mesh-1 CFL=2",
        "Fig.6(b) Tangential force [kN/m], R15Mesh-1 URANS CFL=2, V=10 m/s",
        "kN/m", np.asarray(DEOLIV_CT_CFL2_R_M) / ROTOR_RADIUS, DEOLIV_CT_CFL2,
    )
    _print_digitized(
        "de Oliveira OMAE2023-105084 Fig.6(b) Tangential force, OpenFAST",
        "Fig.6(b) Tangential force [kN/m], OpenFAST-AeroDyn v15, V=10 m/s",
        "kN/m", np.asarray(DEOLIV_CT_FAST_R_M) / ROTOR_RADIUS, DEOLIV_CT_FAST,
    )
    _print_digitized(
        "Yi 2026 Fig.13(a) Present (URANS), ws=9 m/s",
        "Fig.13(a) Normal force per unit length Fn, ws=9 m/s Present",
        "kN/m", YI_FN_PRESENT_RR, YI_FN_PRESENT,
    )
    _print_digitized(
        "Yi 2026 Fig.13(a) BEMT, ws=9 m/s",
        "Fig.13(a) Normal force per unit length Fn, ws=9 m/s BEMT",
        "kN/m", YI_FN_BEMT_RR, YI_FN_BEMT,
    )
    _print_digitized(
        "Yi 2026 Fig.13(b) Present (URANS), ws=9 m/s",
        "Fig.13(b) Torque per unit length Q, ws=9 m/s Present",
        "kN.m/m (torque per unit length; f_t = Q/r)",
        YI_Q_PRESENT_RR, YI_Q_PRESENT,
    )
    _print_digitized(
        "Yi 2026 Fig.13(b) BEMT, ws=9 m/s",
        "Fig.13(b) Torque per unit length Q, ws=9 m/s BEMT",
        "kN.m/m (torque per unit length; f_t = Q/r)",
        YI_Q_BEMT_RR, YI_Q_BEMT,
    )


def _draw_reference(ax, rr, values, ref, width, markersize):
    """Draw one reference curve on ``ax`` with its style."""
    ax.plot(rr, values, color=ref["color"], linewidth=width,
            linestyle=ref["ls"], marker=ref["marker"],
            markersize=markersize, markevery=1, alpha=0.95)


def make_figure(profiles, refs, out_png: Path) -> None:
    """Draw the four-panel three-model comparison and save it."""
    bem_rr = np.array(BEM_RR)
    bem_alpha = np.array(BEM_ALPHA_DEG)
    bem_cn = np.array(BEM_CN)
    bem_ct = np.array(BEM_CT)
    with np.errstate(divide="ignore", invalid="ignore"):
        bem_ratio = np.where(bem_cn != 0.0, bem_ct / bem_cn, np.nan)
    keep = bem_rr <= 1.0
    bem_rr, bem_alpha, bem_cn, bem_ct, bem_ratio = (
        bem_rr[keep], bem_alpha[keep], bem_cn[keep], bem_ct[keep],
        bem_ratio[keep],
    )

    fig = plt.figure(figsize=(14.0, 11.2))
    gs = fig.add_gridspec(2, 2, hspace=0.30, wspace=0.22)
    ax_alpha = fig.add_subplot(gs[0, 0])
    ax_cn = fig.add_subplot(gs[0, 1])
    ax_ct = fig.add_subplot(gs[1, 0])
    ax_ratio = fig.add_subplot(gs[1, 1])
    ax_cn_r = ax_cn.twinx()
    ax_ct_r = ax_ct.twinx()

    model_handles = []
    for label, _, color, marker in MODELS:
        profile = next((p for p in profiles if p["label"] == label), None)
        if profile is None:
            continue
        rr = profile["rr"]
        for ax, values in (
            (ax_alpha, profile["alpha"]),
            (ax_cn, profile["cn"]),
            (ax_ct, profile["ct"]),
            (ax_ratio, profile["ratio"]),
        ):
            ax.plot(rr, values, color=color, linewidth=1.6, marker=marker,
                    markersize=3.2, markevery=6, label=label)
        ax_cn_r.plot(rr, profile["cn"] / bem_at(BEM_CN, rr), color=color,
                     linewidth=1.0, linestyle="--", alpha=0.85)
        ax_ct_r.plot(rr, profile["ct"] / bem_at(BEM_CT, rr), color=color,
                     linewidth=1.0, linestyle="--", alpha=0.85)
        model_handles.append(
            Line2D([], [], color=color, linewidth=1.6, marker=marker,
                   markersize=3.2, label=label)
        )

    bem_handle = Line2D([], [], color=BEM_COLOR, linewidth=1.6,
                        linestyle="--", label="CCBlade BEM")
    ax_alpha.plot(bem_rr, bem_alpha, color=BEM_COLOR, linewidth=1.6,
                  linestyle="--")
    ax_cn.plot(bem_rr, bem_cn, color=BEM_COLOR, linewidth=1.6, linestyle="--")
    ax_ct.plot(bem_rr, bem_ct, color=BEM_COLOR, linewidth=1.6, linestyle="--")
    ax_ratio.plot(bem_rr, bem_ratio, color=BEM_COLOR, linewidth=1.6,
                  linestyle="--")

    # Digitized blade-resolved references on the coefficient panels only.
    ref_handles = []
    for ref in refs:
        _draw_reference(ax_cn, ref["rr_cn"], ref["cn"], ref, 1.1, 3.0)
        _draw_reference(ax_ct, ref["rr_ct"], ref["ct"], ref, 1.1, 3.0)
        ref_handles.append(
            Line2D([], [], color=ref["color"], linewidth=1.1,
                   linestyle=ref["ls"], marker=ref["marker"],
                   markersize=3.0, label=ref["label"])
        )

    ratio_handle = Line2D([], [], color=RATIO_COLOR, linewidth=1.0,
                          linestyle="--", label="model/BEM (right axis)")
    ax_cn_r.axhline(1.0, color=RATIO_COLOR, linewidth=0.9, linestyle=":")
    ax_ct_r.axhline(1.0, color=RATIO_COLOR, linewidth=0.9, linestyle=":")

    for ax in (ax_alpha, ax_cn, ax_ct, ax_ratio):
        ax.grid(True, alpha=0.3, linewidth=0.6)
        ax.set_xlim(0.0, 1.0)
    ax_cn_r.set_ylim(0.0, 2.2)
    ax_ct_r.set_ylim(0.0, 2.4)
    for ax, lab in ((ax_cn_r, r"$c_n$ model/BEM  [-]"),
                    (ax_ct_r, r"$c_t$ model/BEM  [-]")):
        ax.set_ylabel(lab, color=RATIO_COLOR)
        ax.tick_params(axis="y", colors=RATIO_COLOR)

    ax_alpha.set_ylabel(r"$\alpha$  [deg]")
    ax_cn.set_ylabel(r"$c_n$  [-]")
    ax_ct.set_ylabel(r"$c_t$  [-]")
    ax_ratio.set_ylabel(r"$c_t/c_n$  [-]")
    for ax in (ax_alpha, ax_cn, ax_ct, ax_ratio):
        ax.set_xlabel(r"$r/R$  [-]")

    ax_alpha.set_title(r"(a) local angle of attack $\alpha$", fontsize=11)
    ax_cn.set_title(r"(b) normal/thrust coefficient $c_n$ and $c_n/c_n^{BEM}$",
                    fontsize=11)
    ax_ct.set_title(r"(c) tangential/torque coefficient $c_t$ and "
                    r"$c_t/c_t^{BEM}$", fontsize=11)
    ax_ratio.set_title(r"(d) torque-to-thrust ratio $c_t/c_n$ "
                       "(normalisation-free)", fontsize=11)
    ax_alpha.set_ylim(bottom=0.0)

    # Panel (a): per-model mean BEM offset over the annotation span.
    lines = []
    for label, _, color, _ in MODELS:
        profile = next((p for p in profiles if p["label"] == label), None)
        if profile is None:
            continue
        rr = profile["rr"]
        mask = (rr >= ANNOTATE_LO) & (rr <= ANNOTATE_HI)
        d_alpha = profile["alpha"][mask] - bem_at(BEM_ALPHA_DEG, rr)[mask]
        lines.append((label, color, d_alpha.mean(), d_alpha.min(),
                      d_alpha.max()))
    text = "\n".join(
        f"{label}: mean {mean:+.2f} deg  "
        f"({lo:+.2f} .. {hi:+.2f})"
        for label, _, mean, lo, hi in lines
    )
    ax_alpha.annotate(
        f"$\\Delta\\alpha$ vs BEM, r/R in [{ANNOTATE_LO:g}, {ANNOTATE_HI:g}]\n"
        + text,
        xy=(0.03, 0.72), xycoords="axes fraction", fontsize=8.5,
        bbox={"boxstyle": "round", "fc": "white", "ec": "0.6", "alpha": 0.9},
    )

    handles = model_handles + [bem_handle, ratio_handle] + ref_handles
    fig.legend(handles=handles, loc="upper center", ncol=5,
               fontsize=8.5, framealpha=0.9, bbox_to_anchor=(0.5, 0.945))

    fig.suptitle(
        "IEA 15-240-RWT spanwise comparison: ALM vs ASM vs ASM-mesh vs "
        "CCBlade BEM\n"
        f"V = {V_RATED:g} m/s   {RPM_RATED:g} rpm   pitch 0$^\\circ$   "
        f"uniform inflow   precone {PRECONE_DEG:g}$^\\circ$   "
        f"TSR {TSR_RATED:g}",
        fontsize=13, y=0.995,
    )

    caption = []
    for profile in profiles:
        t_start, t_end, period = profile["window"]
        caption.append(
            f"{profile['label']} [{t_start:.1f}, {t_end:.1f}] s "
            f"({(t_end - t_start) / period:.1f} rev, "
            f"{profile['revs_to_end']:.1f} rev to date)"
        )
    fig.text(
        0.5, 0.010,
        "Windows: last 2 revs per run (same rule, run-specific times):\n"
        + "   ".join(caption)
        + ".  No extrapolation: each model is plotted only where its live\n"
        "transient data exists (ASM-mesh is the shortest, ~4 rev).  "
        "References (de Oliveira Fig.6, Yi Fig.13) are VISUALLY DIGITIZED\n"
        "from the published figures (+/-10 %), rescaled to 10.659 m/s and "
        "converted to coefficients.",
        ha="center", va="bottom", fontsize=8, color="0.3",
    )

    fig.subplots_adjust(left=0.070, right=0.925, top=0.885, bottom=0.100)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def make_reference_figure(profiles, refs, out_png: Path) -> None:
    """Two panels: our three models against the digitized references only.

    No BEM and no ratio axes here -- this figure isolates the model-vs-
    blade-resolved-reference comparison in the coefficient panels.
    """
    fig, (ax_cn, ax_ct) = plt.subplots(1, 2, figsize=(13.0, 7.2))

    handles = []
    for label, _, color, marker in MODELS:
        profile = next((p for p in profiles if p["label"] == label), None)
        if profile is None:
            continue
        ax_cn.plot(profile["rr"], profile["cn"], color=color, linewidth=1.7,
                   marker=marker, markersize=3.2, markevery=6)
        ax_ct.plot(profile["rr"], profile["ct"], color=color, linewidth=1.7,
                   marker=marker, markersize=3.2, markevery=6)
        handles.append(
            Line2D([], [], color=color, linewidth=1.7, marker=marker,
                   markersize=3.2, label=label)
        )

    for ref in refs:
        _draw_reference(ax_cn, ref["rr_cn"], ref["cn"], ref, 1.4, 4.0)
        _draw_reference(ax_ct, ref["rr_ct"], ref["ct"], ref, 1.4, 4.0)
        handles.append(
            Line2D([], [], color=ref["color"], linewidth=1.4,
                   linestyle=ref["ls"], marker=ref["marker"],
                   markersize=4.0, label=ref["label"])
        )

    for ax, ylabel, title in (
        (ax_cn, r"$c_n$  [-]",
         r"(a) normal/thrust coefficient $c_n$  (references digitized)"),
        (ax_ct, r"$c_t$  [-]",
         r"(b) tangential/torque coefficient $c_t$  (references digitized)"),
    ):
        ax.grid(True, alpha=0.3, linewidth=0.6)
        ax.set_xlim(0.0, 1.0)
        ax.set_xlabel(r"$r/R$  [-]")
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=11)
    ax_cn.set_ylim(bottom=0.0)
    ax_ct.set_ylim(bottom=0.0)

    fig.legend(handles=handles, loc="upper center", ncol=4, fontsize=8.5,
               framealpha=0.9, bbox_to_anchor=(0.5, 0.905))
    fig.suptitle(
        "IEA 15-240-RWT spanwise: ALM / ASM / ASM-mesh vs blade-resolved "
        "references\n"
        f"V = {V_RATED:g} m/s   {RPM_RATED:g} rpm   pitch 0$^\\circ$   "
        f"uniform inflow   precone {PRECONE_DEG:g}$^\\circ$   "
        f"TSR {TSR_RATED:g}   |   references rescaled from their own "
        "wind speed by $(V/V_{ref})^2$",
        fontsize=12, y=0.985,
    )
    fig.text(
        0.5, 0.010,
        "DIGITIZED references (+/-10 %): de Oliveira OMAE2023-105084 "
        f"Fig.6 (10 m/s URANS CFL=2 and OpenFAST, x{REF_RESCALE_DEOLIV:.3f})"
        ", Yi 2026 Fig.13 ws=9 m/s (Present URANS and BEMT, "
        f"x{REF_RESCALE_YI:.3f}).  Forces per unit span (kN/m; Yi Q is\n"
        "torque per unit length -> f_t = Q/r), converted to coefficients "
        "with W(r)=sqrt(V^2+(Omega r)^2) and the blade chord.",
        ha="center", va="bottom", fontsize=8, color="0.3",
    )
    fig.subplots_adjust(left=0.060, right=0.985, top=0.775, bottom=0.115,
                        wspace=0.18)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revs", type=float, default=DEFAULT_REVS)
    parser.add_argument("--rpm", type=float, default=RPM_RATED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    profiles = []
    for label, run_dir, _, _ in MODELS:
        try:
            profiles.append(load_profile(label, run_dir, args.revs, args.rpm))
        except FileNotFoundError as error:
            print(f"warning: {label}: {error}")

    if not profiles:
        print("error: none of the three runs provided data", flush=True)
        return 1

    print_model_report(profiles)
    print_station_table(profiles)
    print_offsets(profiles)
    print_digitized_tables()

    chord_table = load_chord_table(BLADE_CSV)
    if chord_table[0].size:
        refs = reference_series(chord_table)
    else:
        print(f"warning: {BLADE_CSV}: no chord table; references skipped")
        refs = []

    make_figure(profiles, refs, args.out)
    print(f"\nwrote {args.out.resolve()} ({args.out.stat().st_size} bytes)")
    make_reference_figure(profiles, refs, REFERENCES_OUT)
    print(f"wrote {REFERENCES_OUT.resolve()} "
          f"({REFERENCES_OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
