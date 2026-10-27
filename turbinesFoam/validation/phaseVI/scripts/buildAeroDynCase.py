#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write a self-contained OpenFAST v5.0.0 AeroDyn-driver case for NREL Phase VI.

The case is the code-to-code arbiter of the v1.3 ALM: a rigid, tower-less
two-blade rotor in uniform steady inflow with the ALM's blade table (chord and
twist exactly as the ALM elements under the v1.3 `tip` pitch reference), the
v1.3 OSU total polar (one table, no Reynolds interpolation, like
`liftReCorrExp 0`), the ALM `cylinder` profile (Cl 0, Cd 1.1) inboard of the
airfoil start, and the rotor speed and air density of the measured point.

Two wake models: `bem` (AeroDyn `Wake_Mod=1`, BEMT) and `olaf` (`Wake_Mod=3`,
free vortex wake). `case.json` records every derived input with its source.
Option choices and their reasons: `openfast/README.md`.

Usage:
    buildAeroDynCase.py --sequence S --speed 7 --wake bem --out DIR
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(SCRIPTS))

import comparePhaseVI  # noqa: E402
import element_data  # noqa: E402
from case_config import load_config, select_speed  # noqa: E402

CASE_YAML = ROOT / "config" / "case.yaml"
POLAR = ROOT / "data" / "polars" / "S809_OSU_Re1M_total.dat"
#: The enriched archive tables (S 5-8 m/s, H 7 m/s) the v1.3 gate comparison reads (`--experiment`).
EXPERIMENT = ROOT / "data" / "experiment" / "uae6-archive"

#: Equispaced element layout of the v1.3 gate runs (`run.json` `blade_dz`, registry `metadata.blade_dz`).
BLADE_DZ = 0.05
#: The ALM `cylinder` profile (`generate_case.py`: `data ((-180 0 1.1 0) (180 0 1.1 0))`).
CYLINDER_CD = 1.1
HUB_HEIGHT = 12.192  # config/case.yaml turbine.hub_height; inert with uniform inflow and no tower
AIRFOIL_IDS = {"cylinder": 1, "S809": 2}
#: Linear interpolation of the table, as the ALM's `profileData` does.
POLAR_INTERP_ORDER = 1

#: BEM: steady, so whole revolutions at 10 deg per output step only fix the averaging window.
BEM_STEPS_PER_REV = 36
BEM_REVOLUTIONS = 3
#: OLAF guidelines (OpenFAST docs, aerodyn-olaf/RunningOLAF): 6 deg per step, wake of at least
#: 4 D and 10 revolutions, near wake only with a frozen tail, regularisation 0.6 of the span step.
OLAF_DPSI_DEG = 6.0
OLAF_AVERAGING_REVOLUTIONS = 4
OLAF_CONVECTION_FRACTION = 0.5  # U0 (1 - k_a a) with k_a a = 0.5, the guideline estimate
OLAF_WAKE_DIAMETERS = 4.0
OLAF_WAKE_MIN_REVOLUTIONS = 10
OLAF_FREE_WAKE_DIAMETERS = 2.0  # guideline asks for >= 1 D of free near wake
OLAF_REG_FACTOR = 0.6

KINVISC = 1.5e-5  # inert: single airfoil table, AFTabMod 1; only the output Re uses it
SPDSOUND = 340.3  # inert: no unsteady airfoil model


# --- blade ------------------------------------------------------------------


def blade_nodes(cfg: dict) -> list[dict]:
    """AeroDyn nodes = the geometry stations of `element_data.blade_element_rows` (the ALM element rows).

    AeroDyn requires the first node at the blade root (`BlSpn = 0`), so the nodes sit on the
    stations that bound the ALM elements instead of on the element midpoints; chord and
    mounting angle are the ALM values at those stations. AeroDyn positive-to-feather `BlTwist`
    plus the driver `BldPitch` is the opposite sign of the turbinesFoam mounting angle:
    `twist + pitch = -mounting` at every node. Nodes inboard of the ALM cylinder end
    (`ELEMENT_CYLINDER_END`) use the cylinder profile.
    """
    pitch = float(cfg["turbine"]["pitch_deg"])
    nodes = []
    for row in element_data.blade_element_rows(cfg):
        mounting = row[5]
        nodes.append(
            {
                "radius": row[1],
                "chord": row[3],
                "mounting": mounting,
                "twist": -mounting - pitch,
                "airfoil": "cylinder" if row[1] < element_data.ELEMENT_CYLINDER_END - 1e-9 else "S809",
            }
        )
    return nodes


def render_blade_file(nodes: list[dict], hub_radius: float, airfoil_ids: dict[str, int]) -> str:
    lines = [
        "------- AERODYN v5 BLADE DEFINITION INPUT FILE -------------------------------------",
        "NREL Phase VI blade, written by buildAeroDynCase.py (chord and twist as the v1.3 ALM elements)",
        "======  Blade Properties =================================================================",
        f"{len(nodes):<10d}  NumBlNds    - Number of blade nodes used in the analysis (-)",
        "    BlSpn        BlCrvAC        BlSwpAC        BlCrvAng       BlTwist        BlChord    BlAFID    t_c      BlCb     BlCenBn     BlCenBt    BlCpn",
        "     (m)           (m)            (m)            (deg)         (deg)           (m)        (-)     (-)      (-)      (m)         (m)        (-)",
    ]
    for node in nodes:
        lines.append(
            f"{node['radius'] - hub_radius:.9e}  0.0  0.0  0.0  {node['twist']:.9e}  {node['chord']:.9e}"
            f"  {airfoil_ids[node['airfoil']]:d}  0.0  0.0  0.0  0.0  0.0"
        )
    return "\n".join(lines) + "\n"


# --- polars -----------------------------------------------------------------

_ROW = re.compile(r"^\s*\(\s*([^)]*)\)\s*$")


def read_foam_polar(path: Path) -> list[tuple[float, float, float, float]]:
    """Rows `(alpha_deg Cl Cd Cm)` of an OpenFOAM `profileData` table (`(a cl cd cm)` per line)."""
    rows = []
    for line in Path(path).read_text().splitlines():
        match = _ROW.match(line)
        if match:
            values = tuple(float(token) for token in match.group(1).split())
            if len(values) != 4:
                raise ValueError(f"{path}: expected 4 columns in {line!r}")
            rows.append(values)
    if not rows:
        raise ValueError(f"{path}: no polar rows")
    return rows


def cylinder_polar() -> list[tuple[float, float, float, float]]:
    return [(-180.0, 0.0, CYLINDER_CD, 0.0), (0.0, 0.0, CYLINDER_CD, 0.0), (180.0, 0.0, CYLINDER_CD, 0.0)]


def render_airfoil_file(rows: list[tuple[float, float, float, float]], title: str) -> str:
    head = [
        "! ------------ AirfoilInfo v1.01.x Input File ----------------------------------",
        f"! {title}; one table, no Reynolds interpolation, steady (no unsteady-aero data)",
        "! Converted from the OpenFOAM profileData table by buildAeroDynCase.py",
        "! Cm is the table's own column (0 where the source table has none)",
        "! ------------------------------------------------------------------------------",
        f"{POLAR_INTERP_ORDER:<24d} InterpOrd   ! Interpolation order {{1=linear; 3=cubic spline; \"default\"}}",
        "1                        NonDimArea  ! Non-dimensional area of the airfoil (unused)",
        "0                        NumCoords   ! Number of airfoil shape coordinates (none)",
        "NA                       BL_file     ! Boundary-layer file (aeroacoustics only)",
        "1                        NumTabs     ! Number of airfoil tables in this file",
        "! ------------------------------------------------------------------------------",
        "! data for table 1",
        "! ------------------------------------------------------------------------------",
        "1.0                      Re          ! Reynolds number in millions (label only)",
        "0                        Ctrl        ! Control setting",
        "False                    InclUAdata  ! Is unsteady aerodynamics data included in this table?",
        f"{len(rows):<24d} NumAlf      ! Number of data lines in the following table",
        "!    Alpha      Cl      Cd        Cm",
        "!    (deg)      (-)     (-)       (-)",
    ]
    body = [" ".join(f"{value:.10g}" for value in row) for row in rows]
    return "\n".join(head + body) + "\n"


def read_aerodyn_polar(path: Path) -> list[tuple[float, float, float, float]]:
    rows: list[tuple[float, float, float, float]] = []
    count = None
    for line in Path(path).read_text().splitlines():
        if count is None:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "NumAlf":
                count = int(parts[0])
            continue
        if line.lstrip().startswith("!") or not line.strip():
            continue
        values = tuple(float(token) for token in line.split())
        rows.append(values)  # type: ignore[arg-type]
    if count is None or len(rows) != count:
        raise ValueError(f"{path}: NumAlf does not match the table")
    return rows


# --- inputs -----------------------------------------------------------------


def point_inputs(sequence: str, speed: float) -> dict:
    """Per-point inputs from the sources the ALM case and comparePhaseVI use."""
    cfg = load_config(CASE_YAML)
    entry = select_speed(cfg, speed, sequence)
    radius = float(cfg["turbine"]["radius"])
    omega = float(entry["tsr"]) * float(speed) / radius
    experiment, _ = comparePhaseVI.load_experiment(EXPERIMENT, sequence, speed)
    cfg["turbine"]["blade_dz"] = BLADE_DZ
    cfg["turbine"]["pitch_reference"] = element_data.DEFAULT_PITCH_REFERENCE
    blade = element_data.blade_stations(cfg)
    hub_radius = blade[0]["radius"]
    case_yaml = "config/case.yaml"
    return {
        "cfg": cfg,
        "inputs": {
            "wind_speed_m_s": {"value": float(speed), "source": f"--speed (measured point, {entry['row']})"},
            "tsr": {"value": float(entry["tsr"]), "source": f"{case_yaml} kinematics ({entry['row']}), the ALM tipSpeedRatio"},
            "rotor_speed_rpm": {
                "value": omega * 30.0 / math.pi,
                "source": f"tsr * U / R from {case_yaml} (the ALM rotor speed; table rpm {entry['rotor_speed_rpm']})",
            },
            "rho_kg_m3": {
                "value": float(experiment["rho_kg_m3"]),
                "source": f"data/experiment/uae6-archive/sequence_{sequence}_performance.csv rho_kg_m3, row {experiment['file_name']} (comparePhaseVI --rho auto)",
            },
            "rotor_radius_m": {"value": radius, "source": f"{case_yaml} turbine.radius"},
            "hub_radius_m": {"value": hub_radius, "source": "first row of data/geometry/phaseVI_blade.csv = ALM hubRadius (config/model-definition.yaml)"},
            "pitch_deg": {"value": float(cfg["turbine"]["pitch_deg"]), "source": f"{case_yaml} turbine.pitch_deg, v1.3 tip pitch reference"},
            "n_blades": {"value": int(cfg["turbine"].get("n_blades", 2)), "source": f"{case_yaml} turbine.n_blades"},
            "cone_deg": {"value": 0.0, "source": "ALM has no cone (rigid rotor)"},
            "tilt_deg": {"value": 0.0, "source": "ALM has no tilt"},
            "yaw_deg": {"value": 0.0, "source": "uniform axial inflow, 0 deg yaw"},
            "overhang_m": {"value": 0.0, "source": "no tower or nacelle in the ALM (phaseVI/README.md)"},
        },
        "omega": omega,
        "experiment_row": experiment["file_name"],
    }


def olaf_parameters(rpm: float, speed: float, diameter: float) -> dict:
    """Time step, wake length and run length from the OpenFAST OLAF guidelines."""
    period = 60.0 / rpm
    dt = OLAF_DPSI_DEG / (6.0 * rpm)
    uc = OLAF_CONVECTION_FRACTION * speed
    n_distance = math.ceil(OLAF_WAKE_DIAMETERS * diameter / (uc * dt) - 1e-9)
    n_rotation = math.ceil(OLAF_WAKE_MIN_REVOLUTIONS * period / dt - 1e-9)
    n_nw = max(n_distance, n_rotation)
    n_free = min(n_nw, math.ceil(OLAF_FREE_WAKE_DIAMETERS * diameter / (uc * dt) - 1e-9))
    steps_per_rev = round(period / dt)
    n_steps = n_nw + OLAF_AVERAGING_REVOLUTIONS * steps_per_rev
    return {
        "dt_s": dt,
        "dpsi_deg": OLAF_DPSI_DEG,
        "n_nw_panels": n_nw,
        "n_nw_panels_free": n_free,
        "n_fw_panels": 0,
        "wake_length_m": n_nw * dt * uc,
        "wake_length_revolutions": n_nw * dt / period,
        "steps_per_revolution": steps_per_rev,
        "t_max_s": n_steps * dt,
        "n_steps": n_steps,
        "averaging_revolutions": OLAF_AVERAGING_REVOLUTIONS,
        "reg_factor": OLAF_REG_FACTOR,
    }


# --- file renderers ---------------------------------------------------------


def render_driver(inputs: dict, wake: str, dt: float, t_max: float) -> str:
    value = {key: item["value"] for key, item in inputs.items()}
    return f"""----- AeroDyn Driver Input File ---------------------------------------------------------
NREL Phase VI rigid rotor, uniform steady inflow, no tower; written by buildAeroDynCase.py (wake: {wake})
----- Input Configuration ---------------------------------------------------------------
False           Echo         - Echo input parameters to "<rootname>.ech"?
        0       MHK          - MHK turbine type (switch) {{0: not an MHK turbine}}
        1       AnalysisType - {{1: multiple turbines, one simulation}}
{t_max:.10g}     TMax         - Total run time (s)
{dt:.10g}     DT           - Simulation time step (s)
"aerodyn.dat" AeroFile - Name of the primary AeroDyn input file
----- Environmental Conditions ----------------------------------------------------------
{value['rho_kg_m3']:.10g}     FldDens      - Density of working fluid (kg/m^3)
{KINVISC:.6e}     KinVisc      - Kinematic viscosity of working fluid (m^2/s)
{SPDSOUND:.1f}     SpdSound     - Speed of sound in working fluid (m/s)
1.01325e5     Patm         - Atmospheric pressure (Pa) [used only for an MHK turbine cavitation check]
1.7e3     Pvap         - Vapour pressure of working fluid (Pa) [used only for an MHK turbine cavitation check]
0     WtrDpth      - Water depth (m)
----- Inflow Data -----------------------------------------------------------------------
0      CompInflow  - Compute inflow wind velocities (switch) {{0=Steady Wind; 1=InflowWind}}
"unused"  InflowFile  - Name of the InflowWind input file [used only when CompInflow=1]
{value['wind_speed_m_s']:.10g}      HWindSpeed  - Horizontal wind speed [used only when CompInflow=0 and AnalysisType=1] (m/s)
{HUB_HEIGHT}      RefHt       - Reference height for horizontal wind speed [used only when CompInflow=0] (m)
0.0       PLExp       - Power law exponent (0 = uniform inflow) (-)
----- SeaState Data [used only when MHK = 1 or 2] ---------------------------------------
0     CompSeaSt              - Compute wave velocities (switch) {{0=No Waves; 1=SeaState}}
"unused"        SeaStFile              - Name of the SeaState input file [used only when CompSeaSt=1]
----- Turbine Data ----------------------------------------------------------------------
1               NumTurbines  - Number of turbines
----- Turbine(1) ------------------------------------------------------------------------
True    BasicHAWTFormat(1) - Flag to switch between basic or generic input format
0,0,0    BaseOriginInit(1) - Coordinate of tower base in base coordinates (m)
{value['n_blades']:d}           NumBlades(1)    - Number of blades (-)
{value['hub_radius_m']:.10g}    HubRad(1)       - Hub radius (m)
{HUB_HEIGHT}    HubHt(1)        - Hub height (m)
{value['overhang_m']:.1f}    Overhang(1)     - Overhang (m)
{value['tilt_deg']:.1f}    ShftTilt(1)     - Shaft tilt (deg)
{value['cone_deg']:.1f}    Precone(1)      - Blade precone (deg)
1.0     Twr2Shft(1)     - Vertical distance from the tower-top to the rotor shaft (m)
----- Turbine(1) Motion [used only when AnalysisType=1] ---------------------------------
0               BaseMotionType(1)      - Type of motion prescribed for this base {{0: fixed}} (flag)
0               DegreeOfFreedom(1)     - [used only when BaseMotionType=1] (flag)
0               Amplitude(1)           - [used only when BaseMotionType=1] (m or rad)
0               Frequency(1)           - [used only when BaseMotionType=1] (Hz)
""              BaseMotionFileName(1)  - [used only when BaseMotionType=2]
{value['yaw_deg']:.1f}               NacYaw(1)              - Yaw angle (about z_t) of the nacelle (deg)
{value['rotor_speed_rpm']:.12g}     RotSpeed(1)            - Rotational speed of rotor in rotor coordinates (rpm)
{value['pitch_deg']:.10g}               BldPitch(1)            - Blade 1 pitch (deg)
----- Time-dependent Analysis [used only when AnalysisType=2, numTurbines=1] -------------
"unused"         TimeAnalysisFileName - Filename containing time series
----- Combined-Case Analysis [used only when AnalysisType=3, numTurbines=1] -------------
         0  NumCases     - Number of cases to run
HWndSpeed     PLExp       RotSpd       Pitch        Yaw     dT      Tmax  DOF  Amplitude Frequency
(m/s)        (-)          (rpm)        (deg)        (deg)   (s)     (s)    (-)  (m or rad) (Hz)
----- Output Settings -------------------------------------------------------------------
"ES15.8E2"       OutFmt      - Format used for text tabular output, excluding the time channel.
1                OutFileFmt  - Format for tabular (time-marching) output file (switch) {{1: text file [<RootName>.out]}}
0                WrVTK       - VTK visualization data output: (switch) {{0=none}}
1                WrVTK_Type  - VTK visualization data type: (switch) {{1=surfaces}}
2                VTKHubRad   - HubRadius for VTK visualization (m)
-1,-1,-1,2,2,2   VTKNacDim   - Nacelle Dimension for VTK visualization x0,y0,z0,Lx,Ly,Lz (m)
"""


def render_aerodyn(wake: str, n_nodes: int) -> str:
    wake_mod = {"bem": 1, "olaf": 3}[wake]
    return f"""------- AERODYN INPUT FILE --------------------------------------------------------------------------
NREL Phase VI rigid rotor, rigid blades, no tower; written by buildAeroDynCase.py (wake: {wake})
======  General Options  ============================================================================
False         Echo               - Echo the input to "<rootname>.AD.ech"?  (flag)
"default"     DTAero             - Time interval for aerodynamic calculations {{or "default"}} (s)
          {wake_mod}   Wake_Mod           - Wake/induction model (switch) {{0=none, 1=BEMT, 3=OLAF}}
          0   TwrPotent          - Type tower influence on wind based on potential flow around the tower (switch) {{0=none}}
          0   TwrShadow          - Calculate tower influence on wind based on downstream tower shadow (switch) {{0=none}}
False         TwrAero            - Calculate tower aerodynamic loads? (flag)
False         CavitCheck         - Perform cavitation check? (flag)
False         NacelleDrag        - Include Nacelle Drag effects? (flag)
False         CompAA             - Flag to compute AeroAcoustics calculation
"unused"      AA_InputFile       - AeroAcoustics input file [used only when CompAA=true]
======  Environmental Conditions  ===================================================================
"default"     AirDens            - Air density (kg/m^3) (the driver FldDens)
"default"     KinVisc            - Kinematic viscosity of working fluid (m^2/s)
"default"     SpdSound           - Speed of sound in working fluid (m/s)
"default"     Patm               - Atmospheric pressure (Pa) [used only when CavitCheck=True]
"default"     Pvap               - Vapour pressure of working fluid (Pa) [used only when CavitCheck=True]
======  Blade-Element/Momentum Theory Options  ====================================================== [unused when Wake_Mod=0 or 3, except for BEM_Mod]
          2   BEM_Mod            - BEM model {{1=legacy NoSweepPitchTwist, 2=polar}} (switch) [used for all Wake_Mod to determine output coordinate system]
--- Skew correction
          0   Skew_Mod           - Skew model {{0=No skew model, -1=Remove non-normal component for linearization, 1=skew model active}}
False         SkewMomCorr        - Turn the skew momentum correction on or off [used only when Skew_Mod=1]
          0   SkewRedistr_Mod    - Type of skewed-wake correction model (switch) [used only when Skew_Mod=1]
"default"     SkewRedistrFactor  - Constant used in Pitt/Peters skewed wake model [used only when Skew_Mod=1 and SkewRedistr_Mod=1]
--- BEM algorithm
True          TipLoss            - Use the Prandtl tip-loss model? (flag) [unused when Wake_Mod=0 or 3]
True          HubLoss            - Use the Prandtl hub-loss model? (flag) [unused when Wake_Mod=0 or 3]
True          TanInd             - Include tangential induction in BEMT calculations? (flag) [unused when Wake_Mod=0 or 3]
True          AIDrag             - Include the drag term in the axial-induction calculation? (flag) [unused when Wake_Mod=0 or 3]
True          TIDrag             - Include the drag term in the tangential-induction calculation? (flag) [unused when Wake_Mod=0,3 or TanInd=FALSE]
"Default"     IndToler           - Convergence tolerance for BEMT nonlinear solve residual equation {{or "default"}} (-) [unused when Wake_Mod=0 or 3]
        100   MaxIter            - Maximum number of iteration steps (-) [unused when Wake_Mod=0]
--- Shear correction
False         SectAvg           - Use sector averaging (flag)
1             SectAvgWeighting  - Weighting function for sector average {{1=Uniform, default=1}} within a sector centered on the blade (switch) [used only when SectAvg=True]
5             SectAvgNPoints    - Number of points per sectors (-) {{default=5}} [used only when SectAvg=True]
default       SectAvgPsiBwd     - Backward azimuth relative to blade where the sector starts (<=0) {{default=-60}} (deg) [used only when SectAvg=True]
default       SectAvgPsiFwd     - Forward azimuth relative to blade where the sector ends (>=0) {{default=60}} (deg) [used only when SectAvg=True]
--- Dynamic wake/inflow
          0   DBEMT_Mod          - Type of dynamic BEMT (DBEMT) model {{0=No Dynamic Wake}}
         20   tau1_const         - Time constant for DBEMT (s) [used only when DBEMT_Mod=1 or 3]
======  OLAF -- cOnvecting LAgrangian Filaments (Free Vortex Wake) Theory Options  ================== [used only when Wake_Mod=3]
"OLAF.dat"    OLAFInputFileName  - Input file for OLAF [used only when Wake_Mod=3]
======  Unsteady Airfoil Aerodynamics Options  ====================================================
False         AoA34              - Sample the angle of attack (AoA) at the 3/4 chord or the AC point {{default=True}} [always used]
0             UA_Mod             - Unsteady Aero Model Switch (switch) {{0=Quasi-steady (no UA)}}
True          FLookup            - Flag to indicate whether a lookup for f' will be calculated [used only when UA_Mod>0]
3             IntegrationMethod  - Switch to indicate which integration method UA uses [used only when UA_Mod>0]
0             UAStartRad         - Starting radius for dynamic stall (fraction of rotor radius) [used only when UA_Mod>0]
1             UAEndRad           - Ending radius for dynamic stall (fraction of rotor radius) [used only when UA_Mod>0]
======  Airfoil Information =========================================================================
          1   AFTabMod           - Interpolation method for multiple airfoil tables {{1=1D interpolation on AoA (first table only)}}
          1   InCol_Alfa         - The column in the airfoil tables that contains the angle of attack (-)
          2   InCol_Cl           - The column in the airfoil tables that contains the lift coefficient (-)
          3   InCol_Cd           - The column in the airfoil tables that contains the drag coefficient (-)
          4   InCol_Cm           - The column in the airfoil tables that contains the pitching-moment coefficient; use zero if there is no Cm column (-)
          0   InCol_Cpmin        - The column in the airfoil tables that contains the Cpmin coefficient; use zero if there is no Cpmin column (-)
          2   NumAFfiles         - Number of airfoil files used (-)
"cylinder.dat"    AFNames            - Airfoil file names (NumAFfiles lines) (quoted strings)
"S809.dat"
======  Rotor/Blade Properties  =====================================================================
False         UseBlCm            - Include aerodynamic pitching moment in calculations?  (flag)
"blade.dat"    ADBlFile(1)        - Name of file containing distributed aerodynamic properties for Blade #1 (-)
"blade.dat"    ADBlFile(2)        - Name of file containing distributed aerodynamic properties for Blade #2 (-) [unused if NumBl < 2]
"blade.dat"    ADBlFile(3)        - Name of file containing distributed aerodynamic properties for Blade #3 (-) [unused if NumBl < 3]
======  Hub Properties ============================================================================== [used only when MHK=1 or 2]
          0   VolHub             - Hub volume (m^3)
          0   HubCenBx           - Hub center of buoyancy x direction offset (m)
======  Nacelle Properties ========================================================================== [used only when MHK=1 or 2 or when NacelleDrag=True]
          0   VolNac             - Nacelle volume (m^3)
0.0, 0.0, 0.0 NacCenB            - Position of nacelle center of buoyancy from yaw bearing in nacelle coordinates (m)
0, 0, 0       NacArea            - Projected area of the nacelle in X, Y, Z in the nacelle coordinate system (m^2)
0, 0, 0       NacCd              - Drag coefficient for the nacelle areas defined above (-)
0, 0, 0       NacDragAC          - Position of aerodynamic center of nacelle drag in nacelle coordinates (m)
======  Tail Fin Aerodynamics =======================================================================
False         TFinAero           - Calculate tail fin aerodynamics model (flag)
"unused"      TFinFile           - Input file for tail fin aerodynamics [used only when TFinAero=True]
======  Tower Influence and Aerodynamics ============================================================ [used only when TwrPotent/=0, TwrShadow/=0, TwrAero=True, or MHK=1 or 2]
          0   NumTwrNds         - Number of tower nodes used in the analysis  (-)
TwrElev        TwrDiam        TwrCd          TwrTI           TwrCb          TwrCp          TwrCa
(m)            (m)            (-)            (-)             (-)            (-)            (-)
======  Outputs  ====================================================================================
False         SumPrint            - Generate a summary file listing input options and interpolated properties to "<rootname>.AD.sum"? (flag)
          0   NBlOuts             - Number of blade node outputs [0 - 9] (-)
          1                       BlOutNd             - Blade nodes whose values will be output  (-)
          0   NTwOuts             - Number of tower node outputs [0 - 9]  (-)
          1                       TwOutNd             - Tower nodes whose values will be output  (-)
              OutList             - The next line(s) contains a list of output parameters.  See OutListParameters.xlsx for a listing of available output channels, (-)
"RtAeroCp"
"RtAeroCt"
"RtAeroFxh"
"RtAeroPwr"
"RtSpeed"
"RtTSR"
END of OutList section (the word "END" must appear in the first 3 columns of the last OutList line)
---------------------- NODE OUTPUTS --------------------------------------------
2             BldNd_BladesOut  - Number of blades to output all node information at.  Up to number of blades on turbine. (-)
ALL           BldNd_BlOutNd   - Specify a portion of the nodes to output. {{"ALL", "Tip", "Root", or a list of node numbers}} (-)
              OutList_Nodal - The next line(s) contains a list of output parameters.  See OutListParameters.xlsx for a listing of available output channels, (-)
"Alpha"
"Cn"
"Ct"
"Cl"
"Cd"
"AxInd"
"TnInd"
"Vrel"
END (the word "END" must appear in the first 3 columns of this last OutList line in the optional nodal output section)
====================================================================================================
"""


def render_olaf(olaf: dict, circ_ramp_s: float) -> str:
    return f"""--------------------------- FREE WAKE INPUT FILE ----------------------------------------------
Free wake input file for the NREL Phase VI rotor; written by buildAeroDynCase.py from the OpenFAST OLAF guidelines
--------------------------- GENERAL OPTIONS ---------------------------------------------------
default  IntMethod          - Integration method {{1: RK4, 5: Forward Euler 1st order, default: 5}} (switch)
{olaf['dt_s']:.10g}  DTfvw              - Time interval for wake propagation. {{default: dtaero}} (s)
default  FreeWakeStart      - Time when wake is free. (-) value = always free. {{default: 0.0}} (s)
{circ_ramp_s:.10g}  FullCircStart      - Time at which full circulation is reached. {{default: 0.0}} (s)
-------------------------- CIRCULATION SPECIFICATIONS ----------------------------------------
default  CircSolvMethod     - Circulation solving method {{1: Cl-Based, 2: No-Flow Through, 3: Prescribed, default: 1 }}(switch)
default  CircSolvConvCrit   - Convergence criteria {{default: 0.001}} [only if CircSolvMethod=1] (-)
default  CircSolvRelaxation - Relaxation factor {{default: 0.1}} [only if CircSolvMethod=1] (-)
default  CircSolvMaxIter    - Maximum number of iterations for circulation solving {{default: 30}} (-)
"NA"     PrescribedCircFile - File containing prescribed circulation [only if CircSolvMethod=3] (quoted string)
===============================================================================================
--------------------------- WAKE OPTIONS ------------------------------------------------------
------------------- WAKE EXTENT AND DISCRETIZATION --------------------------------------------
{olaf['n_nw_panels']:d}      nNWPanels           - Number of near-wake panels (-)
{olaf['n_nw_panels_free']:d}      nNWPanelsFree       - Number of free near-wake panels (-) {{default: nNWPanels}}
{olaf['n_fw_panels']:d}      nFWPanels           - Number of far-wake panels (-) {{default: 0}}
{olaf['n_fw_panels']:d}      nFWPanelsFree       - Number of free far-wake panels (-) {{default: nFWPanels}}
default FWShedVorticity    - Include shed vorticity in the far wake {{default: False}}
------------------- WAKE REGULARIZATIONS AND DIFFUSION -----------------------------------------
default DiffusionMethod    - Diffusion method to account for viscous effects {{0: None, 1: Core Spreading, "default": 0}}
3       RegDeterMethod     - Method to determine the regularization parameters {{0:  Manual, 1: Optimized, 2: Chord, 3: Span, default: 0 }}
default RegFunction        - Viscous diffusion function {{0: None, 1: Rankine, 2: LambOseen, 3: Vatistas, 4: Denominator, "default": 3}} (switch)
default WakeRegMethod      - Wake regularization method {{1: Constant, 2: Stretching, 3: Age, default: 3}} (switch)
{olaf['reg_factor']:g}     WakeRegFactor      - Wake regularization factor (m or -)
{olaf['reg_factor']:g}     WingRegFactor      - Wing regularization factor (m or -)
1000    CoreSpreadEddyVisc - Eddy viscosity in core spreading methods, typical values 1-1000
------------------- WAKE TREATMENT OPTIONS ---------------------------------------------------
False   TwrShadowOnWake    - Include tower flow disturbance effects on wake convection {{default:false}} [only if TwrPotent or TwrShadow]
default ShearModel         - Shear Model {{0: No treatment, 1: Mirrored vorticity, default: 0}}
------------------- SPEEDUP OPTIONS -----------------------------------------------------------
2       VelocityMethod     - Method to determine the velocity {{1:Segment N^2, 2:Particle tree, 3:Particle N^2, 4:Segment tree, default: 2}}
default TreeBranchFactor   - Branch radius fraction above which a multipole calculation is used {{default: 1.5}} [only if VelocityMethod=2,4]
default PartPerSegment     - Number of particles per segment {{default: 1}} [only if VelocityMethod=2,3]
===============================================================================================
--------------------------- OUTPUT OPTIONS  ---------------------------------------------------
0       WrVTk              - Outputs Visualization Toolkit (VTK) (independent of .fst option) {{0: NoVTK, 1: Write VTK at VTK_fps, 2: Write VTK at init and final, default: 0}} (flag)
1       nVTKBlades         - Number of blades for which VTK files are exported {{0: No VTK per blade, n: VTK for blade 1 to n, default: 0}} (-)
1       VTKCoord           - Coordinate system used for VTK export. {{1: Global, 2: Hub, 3: Both, default: 1}}
0       VTK_fps            - Frame rate for VTK output (frames per second) [only if WrVTK=1]
0       nGridOut           - Number of grid outputs
GridName  GridType  TStart   TEnd    DTGrid   XStart  XEnd   nX   YStart   YEnd   nY   ZStart   ZEnd   nZ
(-)         (-)      (s)     (s)      (s)       (m)    (m)   (-)   (m)     (m)    (-)   (m)     (m)    (-)
===============================================================================================
--------------------------- ADVANCED OPTIONS --------------------------------------------------
===============================================================================================
"""


# --- case -------------------------------------------------------------------


def build_case(sequence: str, speed: float, wake: str, out: Path) -> Path:
    """Write the complete case into the new directory `out`; returns its path."""
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} exists and is not empty")
    point = point_inputs(sequence, speed)
    cfg = point["cfg"]
    inputs = point["inputs"]
    nodes = blade_nodes(cfg)
    rpm = inputs["rotor_speed_rpm"]["value"]
    period = 60.0 / rpm
    hub_radius = inputs["hub_radius_m"]["value"]
    diameter = 2.0 * inputs["rotor_radius_m"]["value"]

    olaf = None
    if wake == "olaf":
        olaf = olaf_parameters(rpm, float(speed), diameter)
        dt, t_max = olaf["dt_s"], olaf["t_max_s"]
        averaging = olaf["averaging_revolutions"]
    else:
        dt = period / BEM_STEPS_PER_REV
        t_max = BEM_REVOLUTIONS * period
        averaging = 1

    out.mkdir(parents=True, exist_ok=True)
    (out / "ad_driver.dvr").write_text(render_driver(inputs, wake, dt, t_max))
    (out / "aerodyn.dat").write_text(render_aerodyn(wake, len(nodes)))
    (out / "blade.dat").write_text(render_blade_file(nodes, hub_radius, AIRFOIL_IDS))
    (out / "S809.dat").write_text(render_airfoil_file(read_foam_polar(POLAR), f"S809 {POLAR.name}"))
    (out / "cylinder.dat").write_text(render_airfoil_file(cylinder_polar(), "ALM cylinder profile (Cl 0, Cd 1.1)"))
    if olaf is not None:
        (out / "OLAF.dat").write_text(render_olaf(olaf, period))

    case = {
        "format": "OpenFAST v5.0.0 AeroDyn driver",
        "sequence": sequence,
        "speed_m_s": float(speed),
        "wake": wake,
        "experiment_row": point["experiment_row"],
        "pitch_reference": element_data.pitch_reference(cfg),
        "blade_dz_m": BLADE_DZ,
        "polar": f"data/polars/{POLAR.name}",
        "inputs": inputs,
        "nodes": nodes,
        "time": {"dt_s": dt, "t_max_s": t_max, "period_s": period, "averaging_revolutions": averaging},
        "olaf": olaf,
        "output": "ad_driver.out",
    }
    (out / "case.json").write_text(json.dumps(case, indent=2) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sequence", choices=("S", "H"), required=True)
    parser.add_argument("--speed", type=float, required=True, help="wind speed in m/s (a measured point of case.yaml)")
    parser.add_argument("--wake", choices=("bem", "olaf"), required=True)
    parser.add_argument("--out", type=Path, required=True, help="new, empty case directory")
    args = parser.parse_args(argv)
    try:
        out = build_case(args.sequence, args.speed, args.wake, args.out)
    except (KeyError, FileExistsError) as exc:
        parser.error(str(exc))
    print(f"wrote {out} ({args.wake}, sequence {args.sequence}, {args.speed:g} m/s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
