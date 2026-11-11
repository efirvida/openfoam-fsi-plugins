# References

Literature behind the models implemented in this repository (mainly `turbinesFoam/`). Each entry has a
key; code comments cite a model as `[Key]` followed by a short citation (authors, journal, year, DOI) and the
equation numbers used, e.g. `// [DagSorensen2020] ... Eq. 23`.

Bibliographic data were checked against the publisher/DOI record on 2026-11-10. Anything that could not be
checked is marked "(not verified)" and repeated in "Not yet verified" at the end. Paths are relative to the
repository root; `FV` abbreviates `turbinesFoam/src/fvOptions`.

## Tip / end-effect corrections

**[DagSorensen2020]** K. O. Dağ, J. N. Sørensen, "A new tip correction for actuator line computations",
*Wind Energy* 23(2):148-160 (2020; online 2019-11-21). DOI 10.1002/we.2419.
- Implemented in: `FV/axialFlowTurbineALSource/axialFlowTurbineALSource.C` (`calcTipCorrection`, Eq. 23 loop),
  `FV/actuatorLineSource/actuatorLineElement/actuatorLineElement.{C,H}` (inflow correction).
- Equations used: 15-19, 21-23.

**[Shen2005]** W. Z. Shen, R. Mikkelsen, J. N. Sørensen, C. Bak, "Tip loss corrections for wind turbine
computations", *Wind Energy* 8(4):457-475 (2005). DOI 10.1002/we.153.
- Implemented in: `FV/axialFlowTurbineALSource/axialFlowTurbineALSource.C` (`endEffectsModel Shen`).
- Equations used: `g = exp[-0.125 (B λ - 21)] + 0.1`. The code computes `g = exp(-c1 (B λ - c2)) + 0.1`, so
  `c1 = +0.125`, `c2 = 21` reproduce it (the sign is carried by the minus in front of `c1`; no inversion).
  The root branch of the same model is the reflected tip constant, not a Shen formula.

**[GlauertPrandtl]** Prandtl-type tip and hub loss factor (`endEffectsModel Glauert`). Primary source not
identified (not verified). The hub form `(B/2)(r - rHub)/rHub` is cited only as the formula AeroDyn builds
(`BEMT.f90`), not as an attribution to Prandtl or Glauert.
- Implemented in: `FV/axialFlowTurbineALSource/axialFlowTurbineALSource.C`.
- Equations used: `f = (2/π) acos(exp(-(B/2)(1/r* - 1)/sin φ))` (tip), hub analogue.

**[Mohammadi2024]** M. M. Mohammadi, H. Olivares-Espinosa, G. P. Navarro Diaz, S. Ivanell, "An actuator sector
model for wind power applications: a parametric study", *Wind Energy Sci.* 9:1305 (2024).
DOI 10.5194/wes-9-1305-2024.
- Implemented in: not implemented; cited in `odd/` analysis notes only (§2 root form).

## Near-tip correction

**[Trigaux2024]** F. Trigaux, T. Villeneuve, G. Dumas, G. Winckelmans, "Near-tip correction functions for the
actuator line method to improve the predicted lift and drag distributions", *J. Fluid Mech.* 989, A1 (2024).
DOI 10.1017/jfm.2024.461. Companion: F. Trigaux, PhD thesis, UCLouvain, 2024 (title/handle not verified).
- Implemented in: `FV/actuatorLineSource/actuatorLineSource.C`, `.../actuatorLineElement/actuatorLineElement.{C,H}`,
  `turbinesFoam/validation/phaseVI/scripts/applyNearTipFunctions.py`; documented in `turbinesFoam/README.md`.
- Equations used: thesis eqs. 3.17-3.31 (3.31: closed-form chord integral), App. C tables.

## Dynamic stall and added mass

**[LeishmanBeddoes1989]** J. G. Leishman, T. S. Beddoes, "A Semi-Empirical Model for Dynamic Stall",
*J. Am. Helicopter Soc.* 34(3):3-17 (1989). DOI 10.4050/jahs.34.3.
- Implemented in: `FV/actuatorLineSource/actuatorLineElement/dynamicStallModels/LeishmanBeddoes*/`.
- Equations used: not itemised in code (not verified).

**[Sheng2008]** W. Sheng, R. A. McD. Galbraith, F. N. Coton, "A Modified Dynamic Stall Model for Low Mach
Numbers", *J. Sol. Energy Eng.* 130(3) (2008). DOI 10.1115/1.2931509. Taken to be the "Sheng et al. (2008)" named
in `LeishmanBeddoesSGC.H` and `LeishmanBeddoesSD.H` (attribution not verified; alternative:
Sheng et al. 2008, *J. Fluids Eng.* 130(10), DOI 10.1115/1.2969450).
- Implemented in: `LeishmanBeddoesSGC`, `LeishmanBeddoesSD`.

**[DyachukPhD]** E. Dyachuk, PhD thesis, Uppsala University, 2015 (title not verified).
- Implemented in: `LeishmanBeddoesSD` (modifications).

**[LB3G]** Third-generation Leishman-Beddoes modifications: source unidentified.
- Implemented in: `LeishmanBeddoes3G`.

**[Strickland1981]** R. Strickland, "A vortex model of the Darrieus turbine: an analytical and experimental
study", 1981 (Sandia report; report number not retrieved, not verified).
- Implemented in: `FV/actuatorLineSource/actuatorLineElement/addedMassModel/addedMassModel.{C,H}`.
- Equations used: flat-plate added mass coefficients `cc`, `cn`, `cm` (numbers not verified).

## Rotational augmentation

**[DuSelig1998]** Z. Du, M. S. Selig, "A 3-D stall-delay model for horizontal axis wind turbine performance
prediction", AIAA-98-0021, 1998 ASME Wind Energy Symposium. DOI 10.2514/6.1998-21.
- Implemented in: `actuatorLineElement.C` (`correctRotationalAugmentation`).
- Equations used: 9-12.

**[Munduate2002]** X. Munduate, PhD thesis, University of Glasgow, 2002 (title not verified).
- Equation used as an independent check of Du-Selig: Eq. 3.6 (`actuatorLineElement.C`).

**[Cespedes2024]** J. F. Céspedes, C. Bak, F. Zahle, "Limitations of lift correction models for thick airfoils
in wind turbine roots", *J. Phys.: Conf. Ser.* 2767:022029 (2024). DOI 10.1088/1742-6596/2767/2/022029
(the "IOP 2024" paper cited in the code). Independent check of Du-Selig, Eq. (3).

**[ChaviaropoulosHansen2000]** P. K. Chaviaropoulos, M. O. L. Hansen, "Investigating Three-Dimensional and
Rotational Effects on Wind Turbine Blades by Means of a Quasi-3D Navier-Stokes Solver", *J. Fluids Eng.*
122(2):330-336 (2000). DOI 10.1115/1.483261.
- Implemented in: `actuatorLineElement.C` (`correctChaviaropoulosHansenRotationalAugmentation`),
  `actuatorLineSource.C`. Constants a = 2.2, h = 1, n = 4.

**[BurgosTafur2020]** B. S. Burgos Tafur, E. Daniele, B. Stoevesandt et al., "On the calibration of rotational
augmentation models for wind turbine load estimation by means of CFD simulations", *Acta Mech. Sin.*
36(2):306-319 (2020). DOI 10.1007/s10409-020-00949-0.
- Implemented in: same as above. Equations used: 1-4.

**[Lindenburg2004]** C. Lindenburg, "Modelling of rotational augmentation based on engineering considerations
and measurements", ECN-RX--04-131, EWEC London 2004. Original not consulted; equations as transcribed in
**[OuakkiArbaoui2023]** (Ouakki & Arbaoui, "Verification, calibration, and validation of stall delay models using
NREL phase VI and MEXICO data", *J. Renew. Sustain. Energy*, DOI 10.1063/5.0104437; authors' initials, volume and
pages not verified).
- Implemented in: `actuatorLineElement.C` (`correctLindenburgRotationalAugmentation`). Equations used: 5-9.

## Force projection / smearing

**[Massie2019]** L. Massie, P. Ouro, T. Stoesser, Q. Luo, "An Actuator Surface Model to Simulate Vertical Axis
Turbines", *Energies* 12(24):4741 (2019). DOI 10.3390/en12244741.
- Implemented in: `FV/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.{C,H}`; `turbinesFoam/README.md`.
- Equations used: Eq. 13, `ε = max(c/4, 4 ∛V)`; the code keeps only the `4 ∛V` branch.

**[Mendoza2019]** (candidate, inferred) V. Mendoza, A. Chaudhari, A. Goude, "Performance and wake comparison of
horizontal and vertical axis wind turbines under varying surface roughness conditions", *Wind Energy*
22:458-472 (2019). DOI 10.1002/we.2299. Its identity as the "Mendoza et al." quoted by Massie et al. is not
verified.

**[Jha2014]** P. K. Jha, M. J. Churchfield, P. J. Moriarty, S. Schmitz, "Guidelines for Volume Force
Distributions Within Actuator Line Modeling of Wind Turbines on Large-Eddy Simulation-Type Grids",
*J. Sol. Energy Eng.* 136(3):031003 (2014). DOI 10.1115/1.4026252.
- Implemented in: `actuatorLineElement.C` (`calcProjectionEpsilon`), as guideline reference.

**[MeyerForsting2019]** A. R. Meyer Forsting, G. R. Pirrung, N. Ramos-García, "A vortex-based tip/smearing
correction for the actuator line", *Wind Energy Sci.* 4:369 (2019). DOI 10.5194/wes-4-369-2019. (Not implemented.)

**[MeyerForsting2020]** Same authors, "Brief communication: A fast vortex-based smearing correction for the
actuator line", *Wind Energy Sci.* 5:349 (2020). DOI 10.5194/wes-5-349-2020. (Not implemented.)

**[Kleine2023]** V. G. Kleine, A. Hanifi, D. S. Henningson, "Non-iterative vortex-based smearing correction for
the actuator line method", *J. Fluid Mech.* 961, A29 (2023). DOI 10.1017/jfm.2023.237. (Not implemented.)

**[MartinezTossas2023]** L. A. Martínez-Tossas, P. Sakievich, M. J. Churchfield et al., "Generalized filtered
lifting line theory for arbitrary chord lengths and application to wind turbine blades", *Wind Energy*
(online 2023-10-09). DOI 10.1002/we.2872 (volume not retrieved). (Not implemented.)

**[Zormpa2024]** M. Zormpa, F. Zilic de Arcos, X. Chen, C. Vogel, R. H. J. Willden, "The Effect of Flow Sampling
on the Robustness of the Actuator Line Method", *Wind Energy* (online 2024-12-12). DOI 10.1002/we.2965
(volume not retrieved).

## Actuator surface

**[YangSotiropoulos2018]** X. Yang, F. Sotiropoulos, "A new class of actuator surface models for wind turbines",
*Wind Energy* (2018). DOI 10.1002/we.2162; arXiv:1702.02108v4 (volume/pages 21(5):285-302 not verified).
- Implemented in: `FV/bladeSurface/bladeSurface{Sampler,Source}.{C,H}`,
  `FV/nacelleSurface/{surfaceSamplerBase,nacelleSurfaceSampler,nacelleSurfaceSource}.{C,H}`,
  `actuatorSurfaceElement.H` (chord-averaged sampling, Sec. 2.1).
- Equations used: 7 (kernel-smoothed velocity), 8 (smoothed four-point cosine kernel), 18 (force distribution),
  19, 21-23 (nacelle normal/tangential force, Schultz-Grunow friction, tangent direction).
  The kernel is credited in the paper to "Yang et al. 2009" (unidentified).
- In code, "paper Eq. 8 / Eq. 18" means this reference. One occurrence is inside a runtime message string
  (`bladeSurfaceSampler.C`, "Valid kernels: cosine (paper Eq. 8)") and is left verbatim by this documentation-only change.

## Reference turbines and experimental data

**[Hand2001]** M. M. Hand, D. A. Simms, L. J. Fingersh, D. W. Jager, J. R. Cotrell, S. Schreck, S. M. Larwood,
"Unsteady Aerodynamics Experiment Phase VI: Wind Tunnel Test Configurations and Available Data Campaigns",
NREL/TP-500-29955 (2001). DOI 10.2172/15000240.

**[Gaertner2020]** E. Gaertner et al., "Definition of the IEA 15-Megawatt Offshore Reference Wind Turbine",
NREL/TP-5000-75698 (2020). DOI 10.2172/1603478.

**[Zahle2024]** F. Zahle, A. Barlas, K. Lønbæk, P. Bortolotti, D. Zalkind, L. Wang, C. Labuschagne,
L. Sethuraman, G. Barter, "Definition of the IEA Wind 22-Megawatt Offshore Reference Wind Turbine",
DTU Wind Energy Report (2024). DOI 10.11581/dtu.00000317.

Somers1997 (NREL/SR-440-6918), Ramsay1995 (NREL/TP-442-7817) and Simms2001: not verified this round.

## Reference codes

**[Shaler2020]** K. Shaler, E. Branlard, A. Platt, "OLAF User's Guide and Theory Manual", NREL/TP-5000-75959
(2020). No DOI.

**[Bachant2016]** P. Bachant, A. Goude, M. Wosnik, "Actuator line modeling of vertical-axis turbines",
arXiv:1605.01449 (2016). turbinesFoam Zenodo DOI not retrieved (not verified).

## Not yet verified

- [GlauertPrandtl]: primary source not identified.
- [LB3G]: source of the third-generation modifications unidentified.
- [Sheng2008]: assumed to be the paper named in the code (alternative J. Fluids Eng. 130(10)).
- [DyachukPhD], [Munduate2002], Trigaux PhD thesis: titles not verified.
- [Strickland1981]: Sandia report number and equation numbers not retrieved.
- [Mendoza2019]: identity as Massie's "Mendoza et al." inferred only.
- [Lindenburg2004]: original not consulted; equations via [OuakkiArbaoui2023] (volume/pages not verified).
- [YangSotiropoulos2018]: volume/pages; the "Yang et al. 2009" kernel source.
- [MartinezTossas2023], [Zormpa2024]: volume/pages not retrieved.
- Somers1997, Ramsay1995, Simms2001, Bachant2016 Zenodo DOI: not verified.
- [LeishmanBeddoes1989]: equation numbers not itemised in the code.
