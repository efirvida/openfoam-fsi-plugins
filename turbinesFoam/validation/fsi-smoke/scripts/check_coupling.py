#!/usr/bin/env python3
"""Assert that the ASM FSI coupling transfers the quantities *correctly*.

It compares the two per-point traces produced by one smoke run:

    fsi-trace-blade<i>.dat   fluid: current vertices, force and displacement
    solid-trace.dat          solid: received force and written displacement

and checks, per time window and per point:

  1. Force conservation: the force the fluid sends reaches the structure
     point by point (the mapping is 1:1, so the arrays must match).
  2. Deformation: the displacement the solid returns reaches the fluid and is
     non-zero (the blade points actually move).
  3. Rotation (when the rotor spins): the fluid vertices rotate about the
     rotor axis by omega*dt per window.

Exit code 0 if every check passes, 1 otherwise.

Usage:
    check_coupling.py <run-dir> [--axis x,y,z] [--origin x,y,z] [--static]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path


def read_fluid_trace(path: Path):
    """Yield (t, points, forces, displacements) per block."""
    blocks = []
    t = None
    pts: list[tuple[float, float, float]] = []
    F: list[tuple[float, float, float]] = []
    U: list[tuple[float, float, float]] = []

    for line in path.read_text().splitlines():
        if line.startswith("#"):
            if t is not None and pts:
                blocks.append((t, pts, F, U))
            parts = line.split()
            # "# t <value> n <count>"
            t = float(parts[2]) if len(parts) >= 3 else None
            pts, F, U = [], [], []
            continue
        if not line.strip():
            continue
        v = [float(x) for x in line.split()]
        # i x y z fx fy fz ux uy uz
        pts.append((v[1], v[2], v[3]))
        F.append((v[4], v[5], v[6]))
        U.append((v[7], v[8], v[9]))

    if t is not None and pts:
        blocks.append((t, pts, F, U))
    return blocks


def read_solid_trace(path: Path):
    """Return {mesh: {step: [(F),(u)]}}."""
    out: dict[str, dict[int, list]] = {}
    for line in path.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        v = line.split()
        step = int(v[0])
        mesh = v[1]
        F = tuple(float(x) for x in v[3:6])
        u = tuple(float(x) for x in v[6:9])
        out.setdefault(mesh, {}).setdefault(step, []).append((F, u))
    return out


def vsub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def vnorm(a):
    return math.sqrt(sum(x * x for x in a))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--axis", default="1,0,0", help="rotor axis x,y,z")
    ap.add_argument("--origin", default="0,0,0", help="rotor origin x,y,z")
    ap.add_argument("--static", action="store_true")
    ap.add_argument("--tol-rel", type=float, default=1e-6)
    ap.add_argument("--disp-lag", type=int, default=1,
                    help="window lag between the solid's written and the "
                         "fluid's read displacement (1 for serial-explicit)")
    args = ap.parse_args(argv[1:])

    run = args.run_dir.resolve()
    axis = tuple(float(x) for x in args.axis.split(","))
    origin = tuple(float(x) for x in args.origin.split(","))
    anorm = math.sqrt(sum(x * x for x in axis))
    axis = tuple(x / anorm for x in axis)

    fluid_files = sorted(run.glob("fsi-trace-blade*.dat"))
    if not fluid_files:
        print(f"FAIL: no fluid trace in {run}")
        return 1
    solid_file = run / "solid-trace.dat"
    if not solid_file.is_file():
        print(f"FAIL: no solid trace in {run}")
        return 1

    solid = read_solid_trace(solid_file)

    ok = True

    fluid: dict[int, list] = {}
    for bf in fluid_files:
        # blade index from the file name
        idx = int(bf.stem.replace("fsi-trace-blade", ""))
        blocks = read_fluid_trace(bf)
        fluid[idx] = blocks

    # Number of windows must agree
    n_windows = min(
        [len(b) for b in fluid.values()]
        + [max((len(v) for v in solid.values()), default=0)]
    )
    print(f"check: {len(fluid_files)} fluid blade(s), {n_windows} coupled windows")

    for idx, blocks in fluid.items():
        mesh = f"Blade{idx}-Solid"
        ssteps = solid.get(mesh, {})
        if not ssteps:
            print(f"FAIL: no solid trace for {mesh}")
            ok = False
            continue

        max_force_err = 0.0
        max_disp_err = 0.0
        max_u = 0.0
        n_pts = 0

        for step in range(min(n_windows, len(blocks))):
            t, pts, F, U = blocks[step]
            sdata = ssteps.get(step)
            if sdata is None:
                continue

            sf = [d[0] for d in sdata]

            if len(sf) != len(F):
                print(f"FAIL: {mesh} step {step}: {len(F)} fluid pts vs "
                      f"{len(sf)} solid pts")
                ok = False
                break

            n_pts = len(F)

            # Force: written by the fluid at k, read by the solid at k
            for i in range(len(F)):
                df = vnorm(vsub(F[i], sf[i]))
                scale = max(1.0, vnorm(F[i]))
                max_force_err = max(max_force_err, df / scale)

            # Displacement: the fluid reads at k what the solid wrote at k-lag
            slag = ssteps.get(step - args.disp_lag)
            if slag is None:
                continue

            su = [d[1] for d in slag]
            if len(su) != len(U):
                print(f"FAIL: {mesh} step {step}: displacement size mismatch")
                ok = False
                break

            for i in range(len(U)):
                du = vnorm(vsub(U[i], su[i]))
                max_disp_err = max(max_disp_err, du)
                max_u = max(max_u, vnorm(su[i]))

        print(f"  {mesh}: {n_pts} pts/window, "
              f"max relative force error {max_force_err:.3e}, "
              f"max displacement error {max_disp_err:.3e} m, "
              f"max|u| {max_u:.3e} m")

        if max_force_err > args.tol_rel:
            print(f"  FAIL: {mesh} force is not conserved point by point "
                  f"({max_force_err:.3e} > {args.tol_rel:.3e})")
            ok = False
        if max_disp_err > max(1e-12, args.tol_rel * max(max_u, 1.0)):
            print(f"  FAIL: {mesh} displacement does not match the fluid field "
                  f"({max_disp_err:.3e} m)")
            ok = False
        if max_u <= 1e-12:
            print(f"  FAIL: {mesh} displacement is zero: the blade did not move")
            ok = False

    # Rotation: the fluid vertices must rotate about the axis
    for idx, blocks in fluid.items():
        if len(blocks) < 2:
            continue
        _, pts0, _, _ = blocks[0]
        _, pts1, _, _ = blocks[-1]

        def angle_about(axis, origin, p):
            # signed angle of p-origin in the plane perpendicular to axis
            r = tuple(p[i] - origin[i] for i in range(3))
            # build an orthogonal basis (e1, e2) of the plane
            ref = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (1.0, 0.0, 0.0)
            e1 = (ref[1] * axis[2] - ref[2] * axis[1],
                  ref[2] * axis[0] - ref[0] * axis[2],
                  ref[0] * axis[1] - ref[1] * axis[0])
            n1 = math.sqrt(sum(x * x for x in e1))
            e1 = tuple(x / n1 for x in e1)
            e2 = (axis[1] * e1[2] - axis[2] * e1[1],
                  axis[2] * e1[0] - axis[0] * e1[2],
                  axis[0] * e1[1] - axis[1] * e1[0])
            x = sum(r[i] * e1[i] for i in range(3))
            y = sum(r[i] * e2[i] for i in range(3))
            return math.atan2(y, x)

        d = []
        for p0, p1 in zip(pts0, pts1):
            a0 = angle_about(axis, origin, p0)
            a1 = angle_about(axis, origin, p1)
            da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
            d.append(abs(da))

        # a rotating rotor turns every radius by the same angle; a static one
        # leaves the angles unchanged
        med = sorted(d)[len(d) // 2] if d else 0.0
        print(f"  Blade{idx}: median per-window rotation over the trace "
              f"{math.degrees(med):.3f} deg")

        if args.static and med > 1e-6:
            print(f"  FAIL: Blade{idx} rotated in a static case")
            ok = False
        if not args.static and med <= 0.0:
            print(f"  FAIL: Blade{idx} did not rotate")
            ok = False

    print("check: PASS" if ok else "check: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
