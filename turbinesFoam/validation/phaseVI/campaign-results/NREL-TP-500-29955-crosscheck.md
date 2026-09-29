# Cross-check: case vs. NREL/TP-500-29955 (Phase VI wind-tunnel report)

**Purpose.** Validate the case configuration and the experimental reference
against the primary NREL Phase VI report *before* any formulation change. This
is the experimental authority for geometry, Sequence H conditions, and the
airfoil polar provenance.

**Source.** NREL/TP-500-29955, *Unsteady Aerodynamics Experiment Phase VI: Wind
Tunnel Test Configurations and Available Data Campaigns* (DOI 10.2172/15000240).
Local verified copy `phasevi_research/verified/29955_nlr.pdf`
(sha256 `822ee980e97780599ad4ec1dc8b4cc8ad41131b0cbbdffa19999d571f6ce4958`).
Read page-by-page (vision render, 310 pp.) so the tables below are the report's
own values, not a summary.

## 1. Machine parameters (report p72) vs. `config/case.yaml`

| Quantity | Report (standard rotor / Sequence H) | Case | Verdict |
|---|---|---|---|
| Rotor diameter | 10.058 m (standard tip) | `diameter: 10.058` | match |
| Rotor radius | 5.029 m | `radius: 5.029` | match |
| Hub height | 12.192 m | `hub_height: 12.192` | match |
| Number of blades | 2 | `n_blades: 2` | match |
| Rotational speed | 71.63 RPM synchronous | per-speed measured (71.878–72.208) | see §3 |
| Rated power | 19.8 kW | — | context |
| Blade tip pitch (Sequence H) | 3° | `pitch_deg: 3.0` | match |
| Cone | 0° (Sequence H) | not modelled | match |
| Tilt | 0° | not modelled | match |
| Rotor overhang | 1.401 m (yaw axis → blade axis) | not modelled | acceptable |
| Cut-in | 6 m/s | lowest speed 7 m/s | context |
| Blade root attach | 0.508 m from centre of rotation | geometry starts 0.5083 m | match |

Other report notes (p72): tip-plate tip = 9.886 m diameter and extended tip =
11.064 m diameter exist as separate rotors; the case uses the **standard** tip.
Pitch was manually set to 0°, 2°, 3°, 4°, 6° across campaigns.

## 2. Rotor geometry (report p73–74, Table A-1) vs. `data/geometry/phaseVI_blade.csv`

- p73: NREL S809, tapered and twisted; cylindrical root extension to the
  airfoil transition at **0.883 m**; blade root attaches **0.508 m** from the
  centre of rotation.
- p74 Table A-1: chord and twist vs. radius, with two span columns
  (r/5.532 and r/5.029). Twist is positive toward feather, zero at
  **3.772 m = 75 % span**. Twist axis is **50 % chord at the root, 30 %** for
  the S809 sections. Radius runs 0.5083 → 5.532 m; chord 0.218 → 0.305 m.
- Our `phaseVI_blade.csv` header states *"Source: NREL/TP-500-29955, Table A-1.
  Standard 5.029 m tip."* It carries `radius_m, chord_m, twist_deg_report,
  chord_mount`, with `chord_mount = 0.50` at the root and `0.30` for the S809
  sections, and ends at `5.0290, 0.3551, -1.815, 0.300`.

Verdict: **geometry matches the report**, including the 50 %/30 % twist-axis
convention. (Report p74's last row is r = 5.532 m for the *extended* tip; our
file correctly stops at the standard 5.029 m.)

## 3. Sequence H conditions (report p27) vs. `kinematics`

Report p27: **Sequence H** = upwind, rigid, **0° cone**, **blade tip pitch 3°**,
**rotor at 72 RPM**, wind 5–25 m/s, 30-s campaigns (0° yaw; yaw sweeps at 7 and
10 m/s). Sequence I = 0° pitch; Sequence J = 6°.

Our `config/case.yaml` derives the per-speed TSR from the measured WDH
workbooks (`wt_loads_statistics.xls`, sheet `ldsmean`, 0° yaw, Sequence H) and
records `rotor_speed_rpm` as informational. Measured RPMs are 71.878 / 72.107 /
72.091 / 72.062 / 72.208 at 7 / 10 / 13 / 15 / 25 m/s — the rig ran at ~72 RPM,
consistent with the report's nominal 71.63 RPM synchronous value.

**The report's own Sequence H pitch is 3°, so our `pitch_deg: 3.0` is correct.**
SOWFA-6's example uses 4.815°; see `SOWFA-6-crosscheck.md` §2.1.

## 4. Airfoil polars (report p79, Tables A-3..A-8) vs. `data/polars/`

- p79 Table A-3: S809 coefficients at **Re = 300,000 (CSU)**, α 0–90°, Cl and Cdp.
- `data/polars/PROVENANCE.md` rebuilds the committed polars from
  NREL/TP-500-29955 **Tables A-3..A-8** plus NREL/TP-442-7817 Tables B1..B4.
  Raw transcriptions `raw/table_A3..A8.csv` are committed; A-3/A-4/A-5 = CSU
  Re 0.3/0.5/0.65e6, A-6/A-7 = OSU Re 0.75/1e6, A-8 = DUT Re 1e6.
- The case uses `S809_OSU_Re1M_total.dat` (OSU Re = 1×10⁶ = report Table A-7).
- The SAL scaffold polar `S809_Re1M_extended` is explicitly **not** used (it
  has four flipped `Cm` signs and unexplained `Cd` values).

## 5. Open items / discrepancies

| Item | Status | Impact |
|---|---|---|
| Nominal 71.63 RPM vs. measured per-speed RPM | Documented; case uses measured | None — the measured value is the right reference |
| Rotor overhang 1.401 m not modelled | Not modelled | Small; upwind rigid rotor, no tower in the ALM domain |
| Polar Re = 1×10⁶ (OSU) vs. report's CSU Re = 0.3×10⁶ table | Deliberate | The report supplies six Re series; we use the one nearest the 72 RPM operating point |
| Wind-tunnel test-section blockage | Documented, not corrected (`README.md`) | SOWFA's domain matches the test section; ours does not — a candidate follow-up |
| Sequence H data are 30-s campaigns | Our averaging window is revs 4→12 | Measurement is a short campaign mean; ours is a periodic mean |

## 6. Conclusion

**Nothing in the case needs to change on account of the report.** Geometry,
Sequence H pitch (3°), 0° cone, blade count and hub height all match; the polar
provenance is traceable to the report's own tables. The remaining discrepancies
are the overhang (unmodelled, minor), the polar Re choice (deliberate), and the
test-section blockage (a documented non-correction, candidate follow-up).

The report is therefore the authority for the experimental reference used by
`scripts/comparePhaseVI.py` and for the geometry/polar inputs; the formulation
questions (tip/root end effects, pitch) are addressed in
`SOWFA-6-crosscheck.md`.
