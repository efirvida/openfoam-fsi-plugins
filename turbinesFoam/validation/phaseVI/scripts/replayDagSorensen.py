#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline replica of the solver's Dag & Sorensen tip correction, with switches.

The replica follows `axialFlowTurbineALSource::calcTipCorrection`
(`turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C`
:735-1060) line by line and the application in `actuatorLineElement::calculateForce`
(`actuatorLineElement.C`:1156, `inflow += w`). The published method is
Dag & Sorensen, Wind Energy 23 (2020) 148-162, Eq. 15-27.

What the solver does, and what the replica assumes
--------------------------------------------------
* `calcTipCorrection` runs at the start of `addSup`, after the rotor was turned to
  time t but BEFORE the blades compute their force. It therefore reads the
  relative velocity and C_L of step t-1 (already containing w(t-1)) at the
  element positions of time t. The element CSV row of time t-1 is the lagged
  state; the row of time t is the result.
* `alpha_deg` (CSV) is the angle of attack of the CORRECTED relative velocity
  (inflow sampled from the CFD field, spanwise part removed, plus w, minus the
  blade velocity). `alpha_geom_deg` is the angle of attack of `freeStream - blade
  velocity` with no induction at all, so it does not give the uncorrected angle.
  The sampled CFD inflow is not written. The replica therefore RECOVERS the
  uncorrected relative velocity as `rel0 = rel_csv(t) - w_replica(t)`; this makes
  the as-implemented replay reproduce the CSV by construction, so only the
  deviations are informative, and the replica itself is validated separately
  (`validate`) against the solver's own `tipCorrectionDebug` line.
* The relative velocity vector is rebuilt in the (axial, tangential) plane from
  `rel_vel_mag`, `alpha_deg`, `alpha_geom_deg` and the geometry: the section
  normal is fixed by `alpha_geom_deg` (twist and pitch need not be known), and the
  radial component of w is neglected in `|rel|` (second order).
* Blades after the first (no CSV) are the first blade turned about the axis.
* `epsilon` is `projectionEpsilon()` when the dictionary entry is 0, i.e.
  `max(2 cbrt(V_cell) meshFactor, chordFactor c, dragFactor cd c / 2)`; the cell
  volume comes from the blockMeshDict (axis-aligned graded blocks).
* End-effect factor is frozen at its CSV value (it is 1 at r/R >= 0.8, tip effects off).

Deviations that can be switched (each independently)
----------------------------------------------------
  smooth   (a) the extra spanwise Gaussian smoothing of Gamma (:816-860); paper: none
  fixed    (b) fixed-point iteration alpha -> C_L(polar) -> Gamma -> w -> alpha
               instead of one explicit pass on the lagged state
  sweep    (c) helix sweep sign reversed (:960-968)
  tip      (d) tip-station extrapolation (1.5/-0.5) of eps, u_x, u_theta replaced by
               holding the end-element values (the station position stays extrapolated)

Subcommands: `replay` (frozen element states of a production run) and `validate`
(replica versus the solver's debug line and element CSV of a small case).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

VSMALL = 1.0e-300
STATIONS_DEFAULT = (0.80, 0.90, 0.95, 0.98)


# --------------------------------------------------------------------------- #
# Minimal OpenFOAM dictionary access
# --------------------------------------------------------------------------- #

def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def block(text: str, key: str, start: int = 0):
    """Return (content, end) of the first `key { ... }` at or after `start`, or None."""
    m = re.compile(r"(?<![\w$])" + re.escape(key) + r"\s*\{").search(text, start)
    if not m:
        return None
    depth, i = 1, m.end()
    while depth and i < len(text):
        depth += (text[i] == "{") - (text[i] == "}")
        i += 1
    return text[m.end():i - 1], i


def numbers(s: str) -> list[float]:
    return [float(v) for v in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", s)]


def get_vector(text: str, key: str) -> np.ndarray:
    m = re.search(r"(?<![\w$])" + key + r"\s*\(([^)]*)\)\s*;", text)
    if not m:
        raise KeyError(key)
    return np.array(numbers(m.group(1)))


def get_scalar(text: str, key: str, default=None) -> float:
    m = re.search(r"(?<![\w$])" + key + r"\s+([-+0-9.eE]+)\s*;", text)
    if not m:
        if default is None:
            raise KeyError(key)
        return default
    return float(m.group(1))


def paren_list(text: str, key: str) -> str:
    """Text inside the balanced parentheses following `key`."""
    m = re.search(r"(?<![\w$])" + key + r"\s*\(", text)
    if not m:
        raise KeyError(key)
    depth, i = 1, m.end()
    while depth:
        depth += (text[i] == "(") - (text[i] == ")")
        i += 1
    return text[m.end():i - 1]


# --------------------------------------------------------------------------- #
# Polar
# --------------------------------------------------------------------------- #

class Polar:
    """`profileData` single-Re table, linear in alpha (liftReCorrExp 0 / no Re correction)."""

    def __init__(self, rows, re_ref=0.0):
        self.re_ref = re_ref
        a = np.array(rows, dtype=float)
        order = np.argsort(a[:, 0], kind="stable")
        self.alpha, self.cl, self.cd = a[order, 0], a[order, 1], a[order, 2]

    def lift(self, alpha_deg):
        return np.interp(alpha_deg, self.alpha, self.cl)

    def drag(self, alpha_deg, re=None):
        """Table drag; with a reference Re the `profileData::updateRe` correction cd / K,
        K = (ln Re_ref - 0.407)^-2.64 / (ln Re - 0.407)^-2.64 (lift is unchanged for liftReCorrExp 0)."""
        cd = np.interp(alpha_deg, self.alpha, self.cd)
        if re is not None and self.re_ref > VSMALL:
            k = (np.log(self.re_ref) - 0.407) ** -2.64 / (np.log(re) - 0.407) ** -2.64
            cd = cd / k
        return cd

    @staticmethod
    def from_text(text: str, re_ref=0.0) -> "Polar":
        rows = [numbers(m) for m in re.findall(r"\(([^()]+)\)", strip_comments(text))]
        return Polar([r[:3] for r in rows if len(r) >= 3], re_ref)


# --------------------------------------------------------------------------- #
# Case description (system/fvOptions)
# --------------------------------------------------------------------------- #

@dataclass
class Rotor:
    origin: np.ndarray
    axis: np.ndarray            # unit
    down: np.ndarray            # unit free-stream direction
    u_inf: float
    omega: float                # rad/s, signed like the solver (velocity = omega axis x r)
    radius: float
    n_blades: int
    blade_azimuth_rad: list     # per blade, relative to blade 1
    wake_turns: int
    wake_step_deg: float
    epsilon_user: float
    free_stream: np.ndarray


@dataclass
class Blade:
    chord: np.ndarray           # per element
    profile: list               # per element
    n: int


def read_case(case_dir: Path, polar_override: Path | None = None):
    """Parse system/fvOptions of a run: rotor, blade 1 chords, profiles and polars."""
    sysdir = Path(case_dir) / "system"
    text = strip_comments((sysdir / "fvOptions").read_text())
    coeffs = block(text, "axialFlowTurbineALSourceCoeffs")[0]
    origin = get_vector(coeffs, "origin")
    axis = get_vector(coeffs, "axis")
    axis = axis / np.linalg.norm(axis)
    fs = get_vector(coeffs, "freeStreamVelocity")
    radius = get_scalar(coeffs, "rotorRadius")
    tsr = get_scalar(coeffs, "tipSpeedRatio")
    u_inf = float(np.linalg.norm(fs))
    tc = block(coeffs, "tipCorrection")[0]
    blades_txt = block(coeffs, "blades")[0]
    names = re.findall(r"(?<![\w$])(blade\d+)\s*\{", blades_txt)
    az = [0.0]
    for nm in names[1:]:
        b = block(blades_txt, nm)[0]
        off = get_scalar(b, "azimuthalOffset", 0.0)
        az.append(math.radians(off))
    rotor = Rotor(
        origin=origin, axis=axis, down=fs / u_inf, u_inf=u_inf,
        omega=tsr * u_inf / radius, radius=radius, n_blades=len(names),
        blade_azimuth_rad=az,
        wake_turns=int(get_scalar(tc, "wakeTurns", 2)),
        wake_step_deg=get_scalar(tc, "wakeAzimuthalStep", 2.0),
        epsilon_user=get_scalar(tc, "epsilon", 0.0), free_stream=fs,
    )
    b1 = block(blades_txt, names[0])[0]
    n_el = int(get_scalar(b1, "nElements"))
    rows = [numbers(m) for m in re.findall(r"\(([^()]+)\)", paren_list(b1, "elementData"))]
    rows = [r for r in rows if len(r) == 6]
    n_seg = len(rows) - 1
    per = n_el // n_seg
    chord = np.zeros(n_el)
    for j in range(n_el):
        s, k = j // per, j % per
        c1, c2 = rows[s][3], rows[s + 1][3]
        chord[j] = c1 + (c2 - c1) / per * k + (c2 - c1) / per / 2
    plist = paren_list(b1, "elementProfiles").split()
    profile = [plist[j * len(plist) // n_el] for j in range(n_el)]
    prof_block = block(coeffs, "profileData")[0]
    polars, gauss = {}, {}
    for nm in set(profile):
        pb = block(prof_block, nm)[0]
        gc = block(pb, "GaussianCoeffs")
        g = gc[0] if gc else ""
        gauss[nm] = (get_scalar(g, "chordFactor", 0.25), get_scalar(g, "dragFactor", 1.0),
                     get_scalar(g, "meshFactor", 2.0))
        inc = re.search(r'#include\s+"([^"]+)"', pb)
        if inc:
            pf = Path(polar_override) if (polar_override and nm != "cylinder") \
                else (sysdir / inc.group(1)).resolve()
            polars[nm] = Polar.from_text(pf.read_text(), get_scalar(pb, "Re", 0.0))
        else:
            polars[nm] = Polar.from_text(paren_list(pb, "data"), get_scalar(pb, "Re", 0.0))
    return rotor, Blade(chord, profile, n_el), polars, gauss


# --------------------------------------------------------------------------- #
# Mesh: cell volume at a point from an axis-aligned graded blockMeshDict
# --------------------------------------------------------------------------- #

class BlockMesh:
    def __init__(self, path: Path):
        text = strip_comments(Path(path).read_text())
        self.scale = get_scalar(text, "scale", get_scalar(text, "convertToMeters", 1.0))
        verts = [numbers(m) for m in re.findall(r"\(([^()]+)\)", paren_list(text, "vertices"))]
        self.verts = np.array(verts) * self.scale
        self.blocks = []
        btxt = paren_list(text, "blocks")
        for m in re.finditer(r"hex\s*\(([^)]*)\)\s*\(([^)]*)\)\s*simpleGrading\s*\(([^)]*)\)", btxt):
            v = [int(x) for x in m.group(1).split()]
            n = [int(x) for x in m.group(2).split()]
            g = numbers(m.group(3))
            p0, p1, p3, p4 = (self.verts[v[0]], self.verts[v[1]], self.verts[v[3]], self.verts[v[4]])
            lo = np.array([p0[0], p0[1], p0[2]])
            hi = np.array([p1[0], p3[1], p4[2]])
            edges = [self._edges(lo[d], hi[d], n[d], g[d]) for d in range(3)]
            self.blocks.append((lo, hi, edges))

    @staticmethod
    def _edges(a, b, n, ratio):
        if abs(ratio - 1.0) < 1e-12 or n == 1:
            return np.linspace(a, b, n + 1)
        r = ratio ** (1.0 / (n - 1))
        w = (b - a) * (r - 1.0) / (r ** n - 1.0) * r ** np.arange(n)
        return a + np.concatenate([[0.0], np.cumsum(w)])

    @property
    def n_cells(self) -> int:
        return sum(int(np.prod([len(e) - 1 for e in b[2]])) for b in self.blocks)

    def cell_volume(self, p) -> float:
        for lo, hi, edges in self.blocks:
            if np.all(p >= lo - 1e-12) and np.all(p <= hi + 1e-12):
                v = 1.0
                for d in range(3):
                    e = edges[d]
                    i = min(max(np.searchsorted(e, p[d], side="right") - 1, 0), len(e) - 2)
                    v *= e[i + 1] - e[i]
                return v
        raise ValueError("point outside the blockMesh: %s" % (p,))


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #

def rotate(v, origin, axis, angle):
    """OpenFOAM `rotateVector` (right-handed Rodrigues about `axis` through `origin`).

    `v` is (3,) or (..., 3); `angle` is a scalar or broadcasts against `v[..., :1]`.
    """
    v = np.asarray(v, dtype=float) - origin
    c, s = np.cos(angle), np.sin(angle)
    cross = np.cross(axis, v)
    dot = (v @ axis)[..., None] if v.ndim > 1 else v @ axis
    return origin + v * c + cross * s + axis * dot * (1.0 - c)


def blade_frame(pos, rotor: Rotor):
    """Radial unit vector, blade-motion unit vector and radius of every element."""
    rel = pos - rotor.origin
    rad = rel - np.outer(rel @ rotor.axis, rotor.axis)
    rho = np.linalg.norm(rad, axis=1)
    e_r = rad / np.maximum(rho, VSMALL)[:, None]
    e_t = np.sign(rotor.omega) * np.cross(rotor.axis, e_r)
    return e_r, e_t, rho


def inplane_state(rotor: Rotor, e_t, rho, rel_mag, alpha_deg, alpha_geom_deg):
    """Rebuild the in-plane relative velocity (u_x, u_t along the blade motion).

    The section normal n = (cos th, sin th) in the basis (downstream, blade motion) is
    fixed by alpha_geom (angle of freestream - blade velocity to the chord line);
    the actual rel then lies at delta' = th - s (pi/2 - alpha).
    """
    vel = abs(rotor.omega) * rho
    delta_g = np.arctan2(-vel, rotor.u_inf)
    ag, a = np.radians(alpha_geom_deg), np.radians(alpha_deg)
    th_plus = delta_g + (np.pi / 2 - ag)
    th_minus = delta_g - (np.pi / 2 - ag)
    use_plus = np.cos(th_plus) >= np.cos(th_minus)
    theta = np.where(use_plus, th_plus, th_minus)
    s = np.where(use_plus, 1.0, -1.0)
    delta = theta - s * (np.pi / 2 - a)
    return theta, rel_mag * np.cos(delta), rel_mag * np.sin(delta)


def alpha_of(theta, ux, ut, ur=0.0):
    """Angle of attack (deg) of a relative velocity (u_x, u_t, u_r): asin(n.rel/|rel|)."""
    mag = np.sqrt(ux * ux + ut * ut + ur * ur)
    arg = (np.cos(theta) * ux + np.sin(theta) * ut) / np.maximum(mag, VSMALL)
    return np.degrees(np.arcsin(np.clip(arg, -1.0, 1.0))), mag


# --------------------------------------------------------------------------- #
# The correction itself
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Switches:
    smooth: bool = True          # (a) as implemented: Gaussian-smooth Gamma along the span
    fixed: bool = False          # (b) as implemented: one explicit pass on the lagged state
    sweep_reverse: bool = False  # (c) as implemented: sweepSign = -sign(omega axis.down)
    tip_hold: bool = False       # (d) as implemented: 1.5 / -0.5 extrapolation at the end stations

    def label(self) -> str:
        tags = []
        if not self.smooth:
            tags.append("a:no-smooth")
        if self.fixed:
            tags.append("b:fixed-point")
        if self.sweep_reverse:
            tags.append("c:sweep-reversed")
        if self.tip_hold:
            tags.append("d:tip-hold")
        return "+".join(tags) if tags else "as-implemented"


def smooth_gamma(points, gamma, eps):
    """Lines 816-860: normalised Gaussian exp(-0.5 (ds/eps_j)^2) of width eps_j (3-D distance)."""
    n = len(gamma)
    if n < 2:
        return gamma.copy()
    out = np.empty(n)
    for j in range(n):
        e = abs(eps[j])
        if e < VSMALL:
            out[j] = gamma[j]
            continue
        ds = np.linalg.norm(points - points[j], axis=1)
        w = np.exp(-0.5 * (ds / e) ** 2)
        out[j] = (w @ gamma) / max(w.sum(), VSMALL)
    return out


def stations(points, gamma, eps, ux, ut, rotor: Rotor, sw: Switches):
    """Vortex stations p = 0..N of one blade (lines 862-935)."""
    n = len(points)
    nst = n + 1
    st_pt = np.zeros((nst, 3))
    st_eps = np.zeros(nst)
    st_tan = np.zeros(nst)
    st_gam = np.zeros(nst)
    st_ok = np.zeros(nst, dtype=bool)
    for p in range(nst):
        if n == 1:
            w0, w1, j0, j1 = 1.0, 0.0, 0, 0
        elif p == 0:
            w0, w1, j0, j1 = 1.5, -0.5, 0, 1
        elif p == n:
            w0, w1, j0, j1 = 1.5, -0.5, n - 1, n - 2
        else:
            w0, w1, j0, j1 = 0.5, 0.5, p - 1, p
        pv = w0 * points[j0] + w1 * points[j1]
        if sw.tip_hold and (p == 0 or p == n):
            a0, a1 = 1.0, 0.0       # flow quantities and eps of the end element only
        else:
            a0, a1 = w0, w1
        eps_v = a0 * eps[j0] + a1 * eps[j1]
        ux_v = a0 * ux[j0] + a1 * ux[j1]
        ut_v = a0 * ut[j0] + a1 * ut[j1]
        rel = pv - rotor.origin
        rvec = rel - (rel @ rotor.axis) * rotor.axis
        rv = np.linalg.norm(rvec)
        phi = math.atan2(ux_v, ut_v)
        st_pt[p], st_eps[p] = pv, eps_v
        st_tan[p] = rv * math.tan(phi)
        gp = 0.0 if p == 0 else gamma[p - 1]
        gn = 0.0 if p == n else gamma[p]
        st_gam[p] = gp - gn
        st_ok[p] = (eps_v >= 0.0) and (abs(ut_v) >= VSMALL)
    return st_pt, st_eps, st_tan, st_gam, st_ok


def wake_segments(st_pt, st_tan, st_ok, rotor: Rotor, sweep_sign):
    """Lines 984-1030: straight wake segments (centre, vector) per station."""
    d_theta = math.radians(rotor.wake_step_deg)
    n_seg = max(1, int(round(rotor.wake_turns * 360.0 / rotor.wake_step_deg)))
    k = np.arange(1, n_seg + 1)
    cen, dl, idx = [], [], []
    for p in range(len(st_pt)):
        if not st_ok[p]:
            continue
        pv = st_pt[p]
        pts = pv[None, :] + (k * st_tan[p] * d_theta)[:, None] * rotor.down[None, :]
        # rotate each point by sweep_sign * k * dTheta about the axis through the origin
        out = rotate(pts, rotor.origin, rotor.axis, (sweep_sign * k * d_theta)[:, None])
        prev = np.vstack([pv[None, :], out[:-1]])
        cen.append(0.5 * (prev + out))
        dl.append(out - prev)
        idx.append(np.full(n_seg, p))
    return np.vstack(cen), np.vstack(dl), np.concatenate(idx)


def trailing_correction(blade_points, gamma, eps, ux, ut, rotor: Rotor, sw: Switches = Switches(),
                        targets=None):
    """Induced-velocity correction (Eq. 23) at the actuator points of blade 0.

    `blade_points` is (nB, N, 3); `gamma`, `eps`, `ux`, `ut` are (nB, N). `ut` is
    u_theta = -(bladeDir . rel) as in the solver. Returns (N, 3) for blade 0, or the
    values at `targets` (M, 3) when given.
    """
    nb = blade_points.shape[0]
    sweep_sign = -np.sign(rotor.omega * (rotor.axis @ rotor.down))
    if sw.sweep_reverse:
        sweep_sign = -sweep_sign
    cens, dls, gams, epss = [], [], [], []
    for i in range(nb):
        g = smooth_gamma(blade_points[i], gamma[i], eps[i]) if sw.smooth else gamma[i].copy()
        st_pt, st_eps, st_tan, st_gam, st_ok = stations(blade_points[i], g, eps[i], ux[i], ut[i], rotor, sw)
        c, d, idx = wake_segments(st_pt, st_tan, st_ok, rotor, sweep_sign)
        cens.append(c)
        dls.append(d)
        gams.append(st_gam[idx])
        epss.append(st_eps[idx])
    cen, dl = np.vstack(cens), np.vstack(dls)
    gw, ep = np.concatenate(gams), np.concatenate(epss)
    pts = blade_points[0] if targets is None else targets
    return induced_velocity(pts, cen, dl, gw, ep)


def induced_velocity(points, cen, dl, gamma_w, eps):
    """Eq. (22)/(23): sum over vortex segments of Gamma/(4 pi) dl x d / |d|^3 exp(-(|d|/eps)^2).

    `cen` and `dl` are the segment centres and vectors, `d` runs from a segment centre to the
    evaluation point, `eps` is the width of the segment's own vortex station.
    """
    out = np.zeros((len(points), 3))
    for t, pact in enumerate(points):
        d = pact[None, :] - cen
        dm = np.linalg.norm(d, axis=1)
        f = gamma_w / np.maximum(dm ** 3, VSMALL) * np.exp(-((dm / eps) ** 2))
        out[t] = (np.cross(dl, d) * f[:, None]).sum(axis=0)
    return out / (4.0 * math.pi)


def turned_blades(points0, rotor: Rotor):
    """Stack the blade-1 geometry with the other blades turned about the axis."""
    return np.stack([rotate(points0, rotor.origin, rotor.axis, a) for a in rotor.blade_azimuth_rad])


# --------------------------------------------------------------------------- #
# Element CSV state
# --------------------------------------------------------------------------- #

def read_element_rows(run_dir: Path, blade: int, n_el: int, keep: int = 4, window=None):
    """Return one {time: row} dict per element, keeping the last `keep` written rows
    (only rows with time inside `window = (t_lo, t_hi)` when given)."""
    from collections import deque
    base = Path(run_dir) / "postProcessing" / "actuatorLineElements"
    series = []
    for j in range(n_el):
        files = sorted(base.glob("*/turbine.blade%d.element%d.csv" % (blade, j)),
                       key=lambda p: float(p.parent.name))
        if not files:
            raise FileNotFoundError("no CSV for blade%d element%d under %s" % (blade, j, base))
        rows = deque(maxlen=keep)
        for f in files:
            with open(f, newline="") as fh:
                for r in csv.DictReader(fh):
                    if window is not None and not window[0] <= float(r["time"]) <= window[1]:
                        continue
                    rows.append({k: float(v) for k, v in r.items()})
        series.append({r["time"]: r for r in rows})
    return series


def state_at(series, time, tol=1e-9):
    """Arrays of the written quantities at `time` (nearest written time within tol)."""
    out = {}
    for key in series[0][next(iter(series[0]))].keys():
        out[key] = np.empty(len(series))
    for j, s in enumerate(series):
        t = min(s, key=lambda x: abs(x - time))
        if abs(t - time) > tol:
            raise KeyError("time %g not written for element %d" % (time, j))
        for key, v in s[t].items():
            out[key][j] = v
    return out


def times_of(series):
    return sorted(series[0].keys())


# --------------------------------------------------------------------------- #
# Projection epsilon
# --------------------------------------------------------------------------- #

def projection_epsilon(rotor, blade, gauss, mesh: BlockMesh | None, pos, cd):
    """`calcProjectionEpsilon` (the width stored by the previous step) per element."""
    eps = np.empty(blade.n)
    for j in range(blade.n):
        cf, df, mf = gauss[blade.profile[j]]
        thr = max(cf * blade.chord[j], df * cd[j] * blade.chord[j] / 2.0)
        eps_mesh = 2.0 * mesh.cell_volume(pos[j]) ** (1.0 / 3.0) * mf
        eps[j] = eps_mesh if eps_mesh > thr else thr
    if rotor.epsilon_user > 0.0:
        eps[:] = rotor.epsilon_user
    return eps


# --------------------------------------------------------------------------- #
# Lagged replay (one pass), fixed-point replay and aerodynamic response
# --------------------------------------------------------------------------- #

@dataclass
class Frozen:
    """Everything the replay needs, at the written time `t` with the lagged state of t-1."""
    t: float
    rotor: Rotor
    blade: Blade
    polars: dict
    pos: np.ndarray             # element positions at t
    e_r: np.ndarray
    e_t: np.ndarray
    rho: np.ndarray
    theta: np.ndarray           # section normal angle (rad) from alpha_geom
    eps: np.ndarray
    eef: np.ndarray             # end-effect factor at t
    # lagged state (t - dt) transported to the azimuth of t
    gamma_lag: np.ndarray
    ux_lag: np.ndarray
    ut_lag: np.ndarray          # u_theta = -(bladeDir_now . rel_lag)
    # solver result at t
    ux_t: np.ndarray
    ut_t: np.ndarray            # velocity component along the blade motion (negative)
    alpha_t: np.ndarray
    cl_t: np.ndarray
    cd_t: np.ndarray
    rel_t: np.ndarray
    alpha_geom: np.ndarray
    nu: np.ndarray              # kinematic viscosity recovered from the CSV (rel c / Re)


def freeze(series, rotor, blade, polars, gauss, mesh, t, t_prev) -> Frozen:
    now, prev = state_at(series, t), state_at(series, t_prev)
    pos = np.stack([now["x"], now["y"], now["z"]], axis=1)
    pos_p = np.stack([prev["x"], prev["y"], prev["z"]], axis=1)
    e_r, e_t, rho = blade_frame(pos, rotor)
    _, e_t_p, rho_p = blade_frame(pos_p, rotor)
    theta, ux_t, ut_t = inplane_state(rotor, e_t, rho, now["rel_vel_mag"], now["alpha_deg"], now["alpha_geom_deg"])
    _, ux_p, ut_p = inplane_state(rotor, e_t_p, rho_p, prev["rel_vel_mag"], prev["alpha_deg"], prev["alpha_geom_deg"])
    cos_dpsi = np.einsum("ij,ij->i", e_t, e_t_p)
    gamma = 0.5 * blade.chord * prev["cl"] * prev["rel_vel_mag"]
    eps = projection_epsilon(rotor, blade, gauss, mesh, pos_p, prev["cd"])
    return Frozen(
        t=t, rotor=rotor, blade=blade, polars=polars, pos=pos, e_r=e_r, e_t=e_t, rho=rho, theta=theta,
        eps=eps, eef=now["end_effect_factor"], gamma_lag=gamma, ux_lag=ux_p, ut_lag=-ut_p * cos_dpsi,
        ux_t=ux_t, ut_t=ut_t, alpha_t=now["alpha_deg"], cl_t=now["cl"], cd_t=now["cd"],
        rel_t=now["rel_vel_mag"], alpha_geom=now["alpha_geom_deg"],
        nu=now["rel_vel_mag"] * blade.chord / now["Re"],
    )


def stack_blades(fr: Frozen, gamma, ux, ut):
    nb = fr.rotor.n_blades
    pts = turned_blades(fr.pos, fr.rotor)
    rep = lambda a: np.tile(a, (nb, 1))
    return pts, rep(gamma), rep(fr.eps), rep(ux), rep(ut)


def lagged_w(fr: Frozen, sw: Switches):
    pts, g, e, ux, ut = stack_blades(fr, fr.gamma_lag, fr.ux_lag, fr.ut_lag)
    return trailing_correction(pts, g, e, ux, ut, fr.rotor, sw)


def apply_w(fr: Frozen, rel0, w):
    """Relative velocity components after adding w; returns alpha_deg, |rel| and the parts."""
    wx = w @ fr.rotor.down
    wt = np.einsum("ij,ij->i", w, fr.e_t)
    wr = np.einsum("ij,ij->i", w, fr.e_r)
    ux, ut = rel0[0] + wx, rel0[1] + wt
    alpha, mag = alpha_of(fr.theta, ux, ut, wr)
    return alpha, mag, ux, ut


def coefficients(fr: Frozen, alpha, mag=None):
    """C_L (polar x end-effect factor) and Re-corrected C_D at `alpha` for relative speed `mag`."""
    mag = fr.rel_t if mag is None else mag
    re = mag * fr.blade.chord / fr.nu
    cl = np.empty_like(alpha)
    cd = np.empty_like(alpha)
    for prof in set(fr.blade.profile):
        m = np.array([p == prof for p in fr.blade.profile])
        cl[m] = fr.polars[prof].lift(alpha[m]) * fr.eef[m]
        cd[m] = fr.polars[prof].drag(alpha[m], re[m])
    return cl, cd


def fixed_point_w(fr: Frozen, rel0, sw: Switches, tol=1e-9, max_iter=500, relax=0.2, w_init=None, r_min=0.5):
    """Iterate alpha -> C_L(polar) -> Gamma -> w -> alpha to convergence at the current azimuth.

    Elements inboard of `r_min` (r/R) are not iterated: their relative velocity and C_L stay
    at the solver values of the written time (the root region is in stall, where the
    undamped map has no stable fixed point, and it is not a tip deviation). Under-relaxation
    `relax` is needed because the undamped map (what one pass per step does in time) is a
    period-3 limit cycle in the frozen state.
    """
    n = fr.blade.n
    active = fr.rho / fr.rotor.radius >= r_min
    w = np.zeros((n, 3)) if w_init is None else w_init.copy()
    hist = []
    for it in range(max_iter):
        alpha, mag, ux, ut = apply_w(fr, rel0, w)
        cl, _ = coefficients(fr, alpha, mag)
        cl = np.where(active, cl, fr.cl_t)
        mag = np.where(active, mag, fr.rel_t)
        ux = np.where(active, ux, fr.ux_t)
        ut = np.where(active, ut, fr.ut_t)
        gamma = 0.5 * fr.blade.chord * cl * mag
        pts, g, e, uxs, uts = stack_blades(fr, gamma, ux, -ut)
        new = trailing_correction(pts, g, e, uxs, uts, fr.rotor, replace(sw, fixed=False))
        step = np.abs((new - w)[active]).max()
        hist.append(step)
        w = np.where(active[:, None], w + relax * (new - w), w)
        if step < tol:
            return w, it + 1, hist
    return w, max_iter, hist


def normal_coefficient(alpha, cl, cd):
    a = np.radians(alpha)
    return cl * np.cos(a) + cd * np.sin(a)


RELAX_SEQUENCE = (1.0, 0.5, 0.2, 0.1)


def _response(fr: Frozen, rel0, w, sw, iterations, residual, relax):
    """Aerodynamic response (angle, C_L, C_D, c_n) of the frozen element set to a correction w."""
    alpha, mag, ux, ut = apply_w(fr, rel0, w)
    cl, cd = coefficients(fr, alpha, mag)
    cn = normal_coefficient(alpha, cl, cd)
    # the experiment normalises by the dynamic pressure of freestream - blade velocity (no induction)
    q_geom = fr.rotor.u_inf ** 2 + (fr.rotor.omega * fr.rho) ** 2
    return dict(
        sw=sw, w=w, alpha=alpha, mag=mag, cl=cl, cd=cd, cn=cn, cn_q=cn * mag ** 2 / q_geom,
        wx=w @ fr.rotor.down, wt=np.einsum("ij,ij->i", w, fr.e_t), wr=np.einsum("ij,ij->i", w, fr.e_r),
        iterations=iterations, residual=residual, relax=relax,
    )


def evaluate(fr: Frozen, configs):
    """Evaluate every switch set on the frozen state; as-implemented first."""
    w_impl = lagged_w(fr, Switches())
    wx = w_impl @ fr.rotor.down
    wt = np.einsum("ij,ij->i", w_impl, fr.e_t)
    rel0 = (fr.ux_t - wx, fr.ut_t - wt)
    results = {}
    for sw in configs:
        if sw.fixed:
            for relax in RELAX_SEQUENCE:
                w, it, hist = fixed_point_w(fr, rel0, sw, relax=relax)
                if hist[-1] < 1e-9:
                    break
        else:
            w, it, hist, relax = lagged_w(fr, sw), 1, [], None
        results[sw.label()] = _response(fr, rel0, w, sw, it, hist[-1] if hist else None, relax)
    results["no-correction"] = _response(fr, rel0, np.zeros_like(w_impl), None, 0, None, None)
    return rel0, w_impl, results


# --------------------------------------------------------------------------- #
# validate: replica versus the solver's debug line and element CSVs
# --------------------------------------------------------------------------- #

DEBUG_RE = re.compile(r"tipCorrectionDebug t=(\S+) maxCorr=(\S+) maxBlade=(\S+) maxElement=(\S+) "
                      r"maxVector=\(([^)]*)\) .*?relVel=\(([^)]*)\) vel=\(([^)]*)\) uX=(\S+) uTheta=(\S+) "
                      r".*?CL=(\S+) chord=(\S+) eps=(\S+) corr=\(([^)]*)\)")


def parse_debug(path: Path):
    out = {}
    for line in Path(path).read_text().splitlines():
        m = DEBUG_RE.search(line)
        if m:
            g = m.groups()
            out[float(g[0])] = dict(
                max_corr=float(g[1]), max_element=int(g[3]), max_vec=np.array(numbers(g[4])),
                rel=np.array(numbers(g[5])), vel=np.array(numbers(g[6])), ux=float(g[7]), uth=float(g[8]),
                cl=float(g[9]), chord=float(g[10]), eps=float(g[11]), corr=np.array(numbers(g[12])),
            )
    return out


def validate_case(case_dir: Path, debug_log: Path, off_case: Path | None = None, blade_no: int = 1,
                  mesh_path: Path | None = None):
    """Replay every written step with a lagged state and compare with the solver."""
    rotor, blade, polars, gauss = read_case(case_dir)
    mesh = BlockMesh(mesh_path or Path(case_dir) / "system" / "blockMeshDict")
    series = read_element_rows(case_dir, blade_no, blade.n, keep=10**6)
    off = read_element_rows(off_case, blade_no, blade.n, keep=10**6) if off_case else None
    dbg = parse_debug(debug_log)
    times = times_of(series)
    report = []
    for k in range(1, len(times)):
        t, tp = times[k], times[k - 1]
        if t not in dbg or dbg[t]["max_corr"] == 0.0:
            continue
        fr = freeze(series, rotor, blade, polars, gauss, mesh, t, tp)
        w = lagged_w(fr, Switches())
        d = dbg[t]
        tip = blade.n - 1
        mags = np.linalg.norm(w, axis=1)
        row = dict(
            time=t,
            tip_corr_solver=d["corr"].tolist(), tip_corr_replica=w[tip].tolist(),
            tip_rel_err=float(np.linalg.norm(w[tip] - d["corr"]) / np.linalg.norm(d["corr"])),
            max_corr_solver=d["max_corr"], max_corr_replica=float(mags.max()),
            max_corr_rel_err=float(abs(mags.max() - d["max_corr"]) / d["max_corr"]),
            max_element_solver=d["max_element"], max_element_replica=int(mags.argmax()),
            eps_solver_tip=d["eps"], eps_replica_tip=float(fr.eps[tip]),
        )
        # the lagged state of the tip rebuilt from the CSV against the debug state
        prev = state_at(series, tp)
        pos_p = np.stack([prev["x"], prev["y"], prev["z"]], axis=1)
        _, e_tp, rho_p = blade_frame(pos_p, rotor)
        _, ux_p, ut_p = inplane_state(rotor, e_tp, rho_p, prev["rel_vel_mag"], prev["alpha_deg"], prev["alpha_geom_deg"])
        row["tip_ux_err"] = float(abs(ux_p[tip] - d["ux"]))
        row["tip_ut_err_vs_debug_rel"] = float(abs(ut_p[tip] - (d["rel"] @ e_tp[tip])))
        if off is not None and k == 1:
            # first corrected step: the uncorrected run has the same sampled inflow
            st_off = state_at(off, t)
            _, ux_o, ut_o = inplane_state(rotor, fr.e_t, fr.rho, st_off["rel_vel_mag"], st_off["alpha_deg"], st_off["alpha_geom_deg"])
            dw_x = fr.ux_t - ux_o
            dw_t = fr.ut_t - ut_o
            wx = w @ rotor.down
            wt = np.einsum("ij,ij->i", w, fr.e_t)
            scale = np.abs(np.hypot(wx, wt)).max()
            row["onoff_max_abs_err_axial"] = float(np.abs(dw_x - wx).max())
            row["onoff_max_abs_err_tangential"] = float(np.abs(dw_t - wt).max())
            row["onoff_relative_to_max_w"] = float(max(np.abs(dw_x - wx).max(), np.abs(dw_t - wt).max()) / scale)
            row["onoff_solver_w_axial"] = dw_x.tolist()
            row["onoff_replica_w_axial"] = wx.tolist()
        report.append(row)
    return report


# --------------------------------------------------------------------------- #
# replay: the production run
# --------------------------------------------------------------------------- #

def interp_station(r_over_R, values, x):
    return float(np.interp(x, r_over_R, values))


def station_table(fr: Frozen, rel0, w_impl, results, stations_rR):
    rR = fr.rho / fr.rotor.radius
    base = results["as-implemented"]
    rows = []
    for label, r in results.items():
        for s in stations_rR:
            f = lambda a: interp_station(rR, a, s)
            d = lambda key: f(r[key]) - f(base[key])
            rows.append(dict(
                switch=label, r_over_R=s,
                w_axial=f(r["wx"]), w_tangential=f(r["wt"]), w_radial=f(r["wr"]),
                d_w_axial=d("wx"), d_w_tangential=d("wt"),
                alpha_deg=f(r["alpha"]), d_alpha_deg=d("alpha"),
                cl=f(r["cl"]), d_cl=d("cl"),
                cn=f(r["cn"]), d_cn=d("cn"), d_cn_pct=100.0 * d("cn") / f(base["cn"]),
                cn_q=f(r["cn_q"]), d_cn_q_pct=100.0 * d("cn_q") / f(base["cn_q"]),
                iterations=r["iterations"],
            ))
    return rows


STANDARD_CONFIGS = (
    Switches(),
    Switches(smooth=False),
    Switches(fixed=True),
    Switches(sweep_reverse=True),
    Switches(tip_hold=True),
    Switches(smooth=False, fixed=True),
)


def sanity(fr: Frozen, results):
    """Identities that must hold if the chain is read correctly."""
    base = results["as-implemented"]
    cl_pol, cd_pol = coefficients(fr, fr.alpha_t, fr.rel_t)
    sel = fr.rho / fr.rotor.radius >= 0.5
    return dict(
        alpha_identity_max_deg_rR_ge_0p5=float(np.abs(base["alpha"] - fr.alpha_t)[sel].max()),
        polar_cl_vs_csv_max_abs=float(np.abs(cl_pol - fr.cl_t)[sel].max()),
        polar_cd_vs_csv_max_abs=float(np.abs(cd_pol - fr.cd_t)[sel].max()),
        max_radial_over_rel_rR_ge_0p5=float((np.abs(base["wr"]) / base["mag"])[sel].max()),
        max_w_over_rel_rR_ge_0p5=float((np.linalg.norm(base["w"], axis=1) / base["mag"])[sel].max()),
    )


def run_replay(args):
    rotor, blade, polars, gauss = read_case(args.run, args.polar)
    mesh = BlockMesh(args.blockmesh or Path(args.run) / "system" / "blockMeshDict")
    window = None if args.time is None else (args.time - 0.0025, args.time + 0.0005)
    series = read_element_rows(args.run, 1, blade.n, window=window)
    times = times_of(series)
    t = args.time if args.time is not None else times[-1]
    i = min(range(len(times)), key=lambda k: abs(times[k] - t))
    t, tp = times[i], times[i - 1]
    fr = freeze(series, rotor, blade, polars, gauss, mesh, t, tp)
    rel0, w_impl, results = evaluate(fr, STANDARD_CONFIGS)
    table = station_table(fr, rel0, w_impl, results, args.stations)
    chk = sanity(fr, results)
    out = dict(
        run=str(args.run), time=t, time_prev=tp, mesh_cells=mesh.n_cells, n_blades=rotor.n_blades,
        omega=rotor.omega, eps_range=[float(fr.eps.min()), float(fr.eps.max())], sanity=chk, rows=table,
        convergence={k: dict(iterations=v["iterations"], residual=v["residual"], relax=v["relax"]) for k, v in results.items() if v["sw"] is not None and v["sw"].fixed},
    )
    if args.compare_run:
        out["compare_run"] = compare_with_uncorrected(args, fr, results["as-implemented"])
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "replay_summary.json").write_text(json.dumps(out, indent=2))
    with open(outdir / "replay_table.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        wr.writeheader()
        wr.writerows(table)
    print_table(out)
    return out


def compare_with_uncorrected(args, fr: Frozen, base):
    """Plausibility only: alpha(D&S run) - alpha(run without D&S) against the replica's w effect."""
    rotor, blade, _, _ = read_case(args.compare_run)
    series = read_element_rows(args.compare_run, 1, blade.n, keep=args.compare_window)
    ts = times_of(series)[-args.compare_window:]
    alpha = np.mean([state_at(series, t)["alpha_deg"] for t in ts], axis=0)
    ag = state_at(series, ts[-1])["alpha_geom_deg"]
    own = read_element_rows(args.run, 1, blade.n, keep=args.compare_window)
    alpha0 = np.mean([state_at(own, t)["alpha_deg"] for t in times_of(own)], axis=0)
    rR = fr.rho / fr.rotor.radius
    rep = {}
    for s in args.stations:
        rep[str(s)] = dict(
            d_alpha_runs=interp_station(rR, alpha0 - alpha, s),
            alpha_ds=interp_station(rR, alpha0, s), alpha_no_ds=interp_station(rR, alpha, s),
            alpha_geom=interp_station(rR, ag, s),
            d_alpha_replica_w=interp_station(rR, base["alpha"] - alpha_of(fr.theta, fr.ux_t - base["wx"], fr.ut_t - base["wt"], 0.0)[0], s),
        )
    return dict(run=str(args.compare_run), window_steps=args.compare_window, stations=rep)


def print_table(out):
    print("run %s  t=%.6g (lagged state t=%.6g)  eps range %.3f..%.3f m  blades %d" % (
        out["run"], out["time"], out["time_prev"], out["eps_range"][0], out["eps_range"][1], out["n_blades"]))
    print("sanity:", json.dumps(out["sanity"]))
    hdr = "%-26s %5s %8s %8s %9s %9s %9s %9s %9s" % ("switch", "r/R", "w_ax", "w_tan", "d_alpha", "d_cl", "d_cn", "d_cn %", "d_cnq %")
    print(hdr)
    for r in out["rows"]:
        print("%-26s %5.2f %8.4f %8.4f %9.4f %9.5f %9.5f %9.3f %9.3f" % (
            r["switch"], r["r_over_R"], r["w_axial"], r["w_tangential"], r["d_alpha_deg"], r["d_cl"], r["d_cn"],
            r["d_cn_pct"], r["d_cn_q_pct"]))


def run_validate(args):
    rep = validate_case(args.case, args.debug_log, args.off_case, mesh_path=args.blockmesh)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep, indent=2))
    worst = max(max(r["tip_rel_err"], r["max_corr_rel_err"]) for r in rep)
    for r in rep:
        print("t=%g tip_rel_err=%.2e max_corr_rel_err=%.2e maxElem solver/replica %d/%d%s" % (
            r["time"], r["tip_rel_err"], r["max_corr_rel_err"], r["max_element_solver"], r["max_element_replica"],
            (" onoff_rel=%.2e" % r["onoff_relative_to_max_w"]) if "onoff_relative_to_max_w" in r else ""))
    print("worst relative error %.3e (tolerance %.1e): %s" % (worst, args.tol, "PASS" if worst <= args.tol else "FAIL"))
    return 0 if worst <= args.tol else 1


def build_parser():
    ap = argparse.ArgumentParser(
        description="Offline replica of the Dag & Sorensen tip correction with per-deviation switches "
                    "(see the module docstring for the assumptions).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("replay", help="frozen element states of a production run -> table per switch")
    rp.add_argument("--run", type=Path, required=True, help="run directory (system/fvOptions, postProcessing/)")
    rp.add_argument("--time", type=float, default=None, help="written time to replay (default: last)")
    rp.add_argument("--stations", type=float, nargs="+", default=list(STATIONS_DEFAULT), help="r/R stations")
    rp.add_argument("--blockmesh", type=Path, default=None, help="blockMeshDict (default: <run>/system/blockMeshDict)")
    rp.add_argument("--polar", type=Path, default=None, help="polar file overriding the #include of the S809 profile")
    rp.add_argument("--compare-run", type=Path, default=None, help="same case without D&S (plausibility only)")
    rp.add_argument("--compare-window", type=int, default=200, help="steps averaged for --compare-run")
    rp.add_argument("--out", type=Path, required=True, help="output directory")
    vp = sub.add_parser("validate", help="replica versus the solver's tipCorrectionDebug line and element CSV")
    vp.add_argument("--case", type=Path, required=True, help="solver case with D&S on and debug true")
    vp.add_argument("--debug-log", type=Path, required=True, help="text with the tipCorrectionDebug lines")
    vp.add_argument("--off-case", type=Path, default=None, help="same case with the correction off (first-step on/off check)")
    vp.add_argument("--blockmesh", type=Path, default=None)
    vp.add_argument("--tol", type=float, default=1.0e-3, help="relative tolerance on tip corr / max corr")
    vp.add_argument("--out", type=Path, required=True)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "replay":
        run_replay(args)
        return 0
    return run_validate(args)


if __name__ == "__main__":
    sys.exit(main())
