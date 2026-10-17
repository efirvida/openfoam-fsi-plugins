# SPDX-License-Identifier: GPL-3.0-or-later
# NREL Phase VI sequence H: external FLOWUnsteady UVLM + rVPM reference.
# Usage: julia --project=ENV -t N phaseVI.jl DB_DIR ds=on|off NREVS TAG
# DB_DIR is built by ../scripts/buildFlowUnsteadyDatabase.py (total or pressure).
# Outputs are exclusively in runs/TAG; existing runs are never overwritten.
# Positive monitor Q denotes extraction only if the independent F dot velocity
# check is positive. Monitor eta is a propeller formula, NOT turbine CP.
import FLOWUnsteady as uns
import FLOWVLM as vlm
import FLOWVPM as vpm
using LinearAlgebra
using TOML

function main(args)
    length(args) == 4 || error("Usage: phaseVI.jl DB_DIR ds=on|off NREVS TAG")
    db = realpath(args[1])
    args[2] in ("ds=on", "ds=off") || error("Expected ds=on or ds=off")
    ds = args[2] == "ds=on"
    nrevs = parse(Float64, args[3])
    isfinite(nrevs) && 0 < nrevs <= 100 || error("NREVS must be finite and in (0,100]")
    tag = args[4]
    occursin(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", tag) || error("TAG must contain only letters, digits, _ or -")
    root = joinpath(@__DIR__, "runs")
    save_path = joinpath(root, tag)
    ispath(save_path) && error("Run already exists: $save_path")

    # Measured H0700000 speed from config/case.yaml, not nominal 72 RPM.
    RPM, U, rho, mu, sound = 71.878, 7.0, 1.2337256, 1.78e-5, 340.3
    # turbine_flag=false on purpose (signScan.jl): with turbine_flag=true the global DistributedLoad has a
    # flipped tangential component (D/L at 0.47R = 0.74 instead of ~0.1; force.velocity < 0), which also
    # corrupts the bound circulation fed to the VPM. The rotor is still a turbine: pitch = -(twist+3),
    # freestream along -x. In this propeller sign convention the torque on the shaft is negative when the
    # rotor extracts power, so the reported turbine torque is -torque (qsign).
    CW, turbine = false, false
    qsign = turbine ? 1.0 : -1.0
    R, Rhub, B, blade_file, precone = uns.read_rotor("phaseVI.csv"; data_path=db)
    precone == 0 || error("This case requires zero precone")
    R == 5.029 && B == 2 || error("Expected Phase VI R=5.029 m and B=2")
    chord, pitch, sweep, height, airfoils, spl_k, spl_s = uns.read_blade(blade_file; data_path=db)
    # Database stores physical twist + 3 deg. FLOWVLM2OCCBlade negates this
    # when turbine_flag=true; supply its negative so alpha = phi - pitch.
    pitch[:, 2] .*= -1
    # FLOWVLM _generate_blade negates sweepdist. A negative database sweep
    # otherwise puts LE *aft* of the axis, not ahead. Convert it here; leave
    # the original database untouched and archive both distributions below.
    sweep[:, 2] .*= -1
    n, steps_per_rev, p_per_step = 50, 72, 2
    nsteps = round(Int, nrevs*steps_per_rev)
    nsteps > 0 || error("NREVS rounds to zero steps")
    ttot = nsteps/steps_per_rev/(RPM/60)
    omega = 2pi*RPM/60
    tsr = omega*R/U
    J = U/(RPM/60*2R)
    sigma = 2.125*2pi*R/(steps_per_rev*p_per_step)
    max_particles = (2n+1)*B*(nsteps+1)*p_per_step + 1
    # FLOWVLM initializes the rotor shaft along global -x.
    Vinf(X, t) = [-U, 0.0, 0.0]

    rotor = uns.generate_rotor(R, Rhub, B, chord, pitch, sweep, height, airfoils;
        data_path=db, read_polar=vlm.ap.read_polar2, xfoil=false,
        turbine_flag=turbine, precone=precone, CW=CW, n=n, blade_r=0.1,
        spline_k=spl_k, spline_s=spl_s, plot_disc=false, verbose=true)

    # Check actual generated geometry, not merely the input sign. LE must be
    # on the negative-x side of the blade's pitch-axis plane; TE is positive.
    blade = vlm.get_blade(rotor, 1)
    all(blade._xlwingdcr .< 0) || error("LE sweep sign check failed")
    all(blade._xtwingdcr .> 0) || error("Pitch axis not between LE and TE")
    # Empirically determine motion direction from FLOWVLM's rotate operation.
    probe = deepcopy(rotor)
    before = vlm.get_blade(probe, 1).Oaxis[2, :]
    vlm.rotate(probe, 0.001)
    after = vlm.get_blade(probe, 1).Oaxis[2, :]
    omega_vector = normalize(cross(before, after))*omega

    system = vlm.WingSystem()
    vlm.addwing(system, "Rotor", rotor)
    wake = vlm.WingSystem()
    vlm.addwing(wake, "Rotor", rotor)
    vehicle = uns.UVLMVehicle(system; rotor_systems=([rotor],), wake_system=wake)
    maneuver = uns.KinematicManeuver((), (t->1.0,), t->zeros(3), t->zeros(3))
    sim = uns.Simulation(vehicle, maneuver, 0.0, RPM, ttot;
        Vinit=zeros(3), Winit=zeros(3))

    # Use FLOWVPM's standard path creation, only after checking nonexistence.
    mkpath(root)
    vpm.create_path(save_path, false)
    cp(db, joinpath(save_path, "database"))
    open(joinpath(save_path, "settings.toml"), "w") do io
        TOML.print(io, Dict("database_source"=>db, "args"=>args,
            "RPM"=>RPM, "U"=>U, "Vinf"=>[-U, 0.0, 0.0], "rho"=>rho, "mu"=>mu, "sound_speed"=>sound,
            "gc_between_steps"=>true,
            "TSR"=>tsr, "CW"=>CW, "turbine_flag"=>turbine, "precone"=>precone,
            "pitch_multiplier"=>-1, "sweep_multiplier"=>-1,
            "omega_vector"=>omega_vector, "n"=>n, "steps_per_rev"=>steps_per_rev,
            "nsteps"=>nsteps, "p_per_step"=>p_per_step, "sigma_rotor_surf"=>R/10,
            "sigma_vpm"=>sigma, "sigmafactor_vpmonvlm"=>1.0, "vlm_rlx"=>0.5,
            "integration"=>"rungekutta3", "SFS"=>"SFS_none", "viscous"=>"Inviscid",
            "apply_correction3D"=>ds, "apply_extrapolate"=>true,
            "hubtiploss"=>"nocorrection", "suppress_fountain"=>true,
            "fountain_radius"=>0.35, "fountain_revs"=>3,
            "shed_starting"=>false, "shed_unsteady"=>true, "unsteady_shedcrit"=>0.001,
            "threads"=>Threads.nthreads(), "julia_version"=>string(VERSION),
            "FLOWUnsteady_source"=>pathof(uns), "FLOWVLM_source"=>pathof(vlm),
            "FLOWVPM_source"=>pathof(vpm)))
    end
    open(joinpath(save_path, "geometry.csv"), "w") do io
        println(io, "r_m,chord_m,input_pitch_deg,input_sweep_m,generated_LE_x_m,generated_TE_x_m")
        for i in eachindex(rotor.r)
            println(io, join((rotor.r[i], rotor.chord[i], rotor.theta[i], rotor.LE_x[i],
                blade._xlwingdcr[i], blade._xtwingdcr[i]), ','))
        end
    end
    monitor = uns.generate_monitor_rotors([rotor], J, rho, RPM, nsteps;
        t_scale=RPM/60, save_path=save_path, run_name=tag,
        disp_conv=false, save_init_plots=false, V_inf=U, turbine=true)
    omit_shedding = Int[]
    start = time_ns()
    open(joinpath(save_path, "power.csv"), "w") do io
        println(io, "rev,wall_s,CT,CQ,CP,Q_Nm,P_monitor_W,P_force_dot_velocity_W,Fx_N")
    end
    function runtime(sim, field, t, dt; optargs...)
        # AirfoilPrep creates Python-backed arrays each step. PyCall's
        # finalizers must run on the calling thread, never a VPM worker.
        # VPM tasks have joined before this callback; collect every step to
        # bound memory while automatic GC is disabled in threaded kernels.
        GC.enable(true)
        GC.gc(false)
        GC.enable(false)
        monitor(sim, field, t, dt; optargs...)
        thrust, torque = vlm.calc_thrust_torque(rotor)
        ct, cq = vlm.calc_thrust_torque_coeffs(rotor, rho, U, true)
        # Integrate physical aerodynamic work using the global force vectors
        # and the measured rotation direction (independent of monitor signs).
        lengths = Float64[2*(rotor._r[1]-rotor.hubR)]
        for i in 2:length(rotor._r)
            push!(lengths, 2*(rotor._r[i]-rotor._r[i-1])-lengths[end])
        end
        power, fx = 0.0, 0.0
        for b in 1:B
            radial = vlm.get_blade(rotor, b).Oaxis[2, :]
            for i in eachindex(lengths)
                force = rotor.sol["DistributedLoad"]["field_data"][b][i]*lengths[i]
                velocity = cross(omega_vector, radial*rotor._r[i])
                power += dot(force, velocity)
                fx += force[1]
            end
        end
        open(joinpath(save_path, "power.csv"), "a") do io
            println(io, join((t*RPM/60, (time_ns()-start)/1e9, ct, qsign*cq,
                qsign*tsr*cq, qsign*torque, qsign*torque*omega, power, fx), ','))
        end
        if sim.nt == 1
            for i in 1:vlm.get_m(rotor)
                cp = vlm.getHorseshoe(rotor, i)[5]
                norm(cp-vlm._get_O(rotor)) <= 0.35R && push!(omit_shedding, i)
            end
        elseif sim.nt == 3steps_per_rev
            omit_shedding .= -1
        end
        return false
    end
    println("PHASEVI_START tag=$tag TSR=$tsr Vinf=$(Vinf(zeros(3),0)) CW=$CW RPM=$RPM turbine=$turbine DS=$ds threads=$(Threads.nthreads())")
    gc_was_enabled = GC.enable(false)
    try
        uns.run_simulation(sim, nsteps;
        Vinf=Vinf, rho=rho, mu=mu, sound_spd=sound,
        max_particles=max_particles, p_per_step=p_per_step,
        vpm_integration=vpm.rungekutta3, vpm_SFS=vpm.SFS_none,
        vpm_viscous=vpm.Inviscid(), sigma_vlm_surf=R/10, sigma_rotor_surf=R/10,
        sigma_vpm_overwrite=sigma, sigmafactor_vpmonvlm=1.0, vlm_rlx=0.5,
        hubtiploss_correction=vlm.hubtiploss_nocorrection,
        apply_correction3D=ds, apply_extrapolate=true,
        shed_starting=false, shed_unsteady=true, unsteady_shedcrit=0.001,
        omit_shedding=omit_shedding, extra_runtime_function=runtime,
        save_path=save_path, run_name=tag, create_savepath=false, prompt=false,
        nsteps_save=steps_per_rev, save_wopwopin=false, save_code=@__FILE__)
    finally
        GC.enable(gc_was_enabled)
    end
    elapsed = (time_ns()-start)/1e9
    println("PHASEVI_DONE wall_s=$elapsed wall_s_per_rev=$(elapsed/(nsteps/steps_per_rev))")
end
main(ARGS)
