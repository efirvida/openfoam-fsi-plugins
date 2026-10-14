# Aerodynamic tares, runs 056 and 058

`runs_056_058.csv` is NREL/TP-500-29955 (Hand et al. 2001), Appendix I, Table I-4 (run 056, tower +
nacelle, blades removed, PDF p. 296-299) and Table I-5 (run 058, tower only, PDF p. 300), parsed by
`scripts/extractAeroTare.py --rows-out`. Report units (deg, slug/ft^3, psf, ft/s, lb, lb ft); raw
balance channels with no tare applied (report, PDF p. 295). Run 058 starts with the balance not zeroed
(lift about 4060 lb on the wind-off and `ATT000000` rows); those rows have `q` below the 5 Pa cut and
are not used.

Use: the nacelle drag area `CdA(056) - CdA(058)` at yaw 0, the integral target of the nacelle
surrogate (`config/nacelle.yaml`, `odd/tasks/nacelle-onoff-study.md`). The report gives no nacelle
fairing geometry.
