# SPDX-License-Identifier: GPL-3.0-or-later
# Which way does a positive FLOWVLM rotation move the blade relative to the blade's local x axis?
# calc_inflow adds +omega*r along the blade-local x axis to the freestream, i.e. the blade moves
# along -x_local. This prints dot(velocity of a positive `rotate`, x_local): -1 means the two
# conventions agree. Usage: julia --project=<env> rotationProbe.jl <database dir>
import FLOWUnsteady as uns
import FLOWVLM as vlm
using LinearAlgebra

db = ARGS[1]
R, Rhub, B, blade_file, _ = uns.read_rotor("phaseVI.csv"; data_path=db)
chord, pitch, sweep, height, airfoils, spl_k, spl_s = uns.read_blade(blade_file; data_path=db)
pitch[:, 2] .*= -1
sweep[:, 2] .*= -1
rotor = uns.generate_rotor(R, Rhub, B, chord, pitch, sweep, height, airfoils; data_path=db,
    read_polar=vlm.ap.read_polar2, xfoil=false, turbine_flag=true, CW=false, n=50, blade_r=0.1,
    spline_k=spl_k, spline_s=spl_s, plot_disc=false)
blade = vlm.get_blade(rotor, 1)
radial0 = blade.Oaxis[2, :]
xlocal0 = blade.Oaxis[1, :]
probe = deepcopy(rotor)
vlm.rotate(probe, 0.001)
radial1 = vlm.get_blade(probe, 1).Oaxis[2, :]
velocity = normalize(radial1 - radial0)
println("PROBE dot(velocity of positive rotate, x_local) = ", round(dot(velocity, xlocal0), digits=4))
println("PROBE axis (radial0 x radial1) = ", normalize(cross(radial0, radial1)))
