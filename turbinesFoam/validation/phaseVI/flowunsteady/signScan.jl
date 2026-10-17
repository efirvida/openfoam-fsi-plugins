# SPDX-License-Identifier: GPL-3.0-or-later
# Wake-free sign scan for the Phase VI turbine in FLOWUnsteady/FLOWVLM: strip theory
# (solvefromCCBlade with a uniform inflow, no induction) for every combination of
# turbine_flag, pitch sign, freestream direction and rotation sense. Cheap (seconds).
# Reports CT, CQ (turbine normalisation), the mean angle of attack at r/R ~ 0.47 and
# the shaft power computed from the section forces and the rotation, which is the
# only unambiguous sign test (power > 0 means the rotor extracts energy).
# Usage: [SCAN_DS=on] [SCAN_FULL=off] julia --project=<env> signScan.jl <database dir>
# SCAN_FULL=off scans only the combination that works (turbine_flag, pitch=-(twist+3), Vinf=-x).
import FLOWUnsteady as uns
import FLOWVLM as vlm

db = ARGS[1]
RPM0, U, rho, sound = 71.878, 7.0, 1.2337256, 340.3
R, Rhub, B, blade_file, _ = uns.read_rotor("phaseVI.csv"; data_path=db)
omega = 2pi * RPM0 / 60
ds = get(ENV, "SCAN_DS", "off") == "on"
full = get(ENV, "SCAN_FULL", "on") == "on"
for turbine in (full ? (true, false) : (true,)), psign in (full ? (1, -1) : (-1,)), vsign in (full ? (1, -1) : (-1,)), cw in (false,)
    chord, pitch, sweep, height, airfoils, spl_k, spl_s = uns.read_blade(blade_file; data_path=db)
    pitch[:, 2] .*= psign
    sweep[:, 2] .*= -1   # FLOWVLM negates sweepdist internally (see phaseVI.jl)
    try
        rotor = uns.generate_rotor(R, Rhub, B, chord, pitch, sweep, height, airfoils;
            data_path=db, read_polar=vlm.ap.read_polar2, xfoil=false, turbine_flag=turbine,
            CW=cw, n=50, blade_r=0.1, spline_k=spl_k, spline_s=spl_s, plot_disc=false)
        Vinf(X, t) = [vsign * U, 0.0, 0.0]
        vlm.solvefromCCBlade(rotor, Vinf, RPM0, rho; sound_spd=sound,
            apply_correction3D=ds, apply_extrapolate=true, verbosewarn=false)
        thrust, torque = vlm.calc_thrust_torque(rotor)
        q = 0.5 * rho * U^2
        A = pi * R^2
        # section forces in the blade-fixed frame: Np normal to the rotor plane, Tp tangential
        # (positive Tp opposes rotation for a propeller). Power = -Q*omega with the CCBlade sign.
        Np = rotor.sol["Np"]["field_data"][1]
        Tp = rotor.sol["Tp"]["field_data"][1]
        mid = argmin(abs.(rotor._r ./ R .- 0.47))
        # Global force on the blade vs the relative flow: drag along the flow must be small and
        # positive (D/L ~ cd/cl); a flipped tangential component breaks this.
        F = rotor.sol["DistributedLoad"]["field_data"][1][mid]
        V = rotor.sol["GlobInflow"]["field_data"][1][mid]
        dunit = V / sqrt(sum(abs2, V))
        drag = sum(F .* dunit)
        lift = sqrt(max(sum(abs2, F) - drag^2, 0.0))
        println("turbine=$turbine psign=$psign vsign=$vsign cw=$cw  CT=$(round(thrust / (q * A), digits=3)) ",
                "CQ=$(round(torque / (q * R * A), digits=4)) Np(0.47R)=$(round(Np[mid], digits=1)) Tp(0.47R)=$(round(Tp[mid], digits=1)) D/L(0.47R)=$(round(drag / lift, digits=3))")
    catch err
        println("turbine=$turbine psign=$psign vsign=$vsign cw=$cw  ERROR ", first(sprint(showerror, err), 300))
    end
end
