# OpenFAST v5 input templates

`ServoDyn_r-test_v5.0.0.dat` is `glue-codes/openfast/5MW_Land_DLL_WTurb/NRELOffshrBsline5MW_Onshore_ServoDyn.dat`
from https://github.com/OpenFAST/r-test at tag v5.0.0 (Apache-2.0). The IEA-15-240-RWT repository ships ServoDyn
v1.05 files that the v5.0.0 binary rejects (first missing key: `PitNeut(1)`). `scripts/openfast_gust.py` keeps this
layout and takes every value the IEA file also defines.

The `IEA-15-240-RWT-OLAF_rated*.dat/.fst` files are the standalone OpenFAST rated-point case (BEMT, fixed rpm) in the v5.0.0 input layout,
copied from `reference/bem-15rev` (git-ignored there) so `scripts/openfast_sweep.py` and `scripts/openfast_gust.py` work from a clean clone.
They contain absolute paths to the IEA-15-240-RWT repository under `/scratch/leahk/eduardo.donestevez/`; edit them on another machine.
