# SPDX-License-Identifier: GPL-3.0-or-later
# Source this on a SDumont login node to build and test the plugins against the
# openfoam/v2506 module (see AGENTS.md "Building on SDumont"):
#
#   . tools/foam-env.sh
#
# On top of the wmake identity variables it handles three facts of that module:
#   * the platform that is installed is linux64GccDPInt64Opt, but the module puts
#     the Int32 directory on PATH, so the Int64 `bin` is prepended;
#   * objects built earlier may need a libstdc++ newer than the module's gcc 9.3,
#     so link time uses gcc 15.2 (LIBRARY_PATH) and run time gcc 15.2/14.2;
#   * the module ships no scotch, metis or KaHIP, only dummy stubs, so those
#     decomposition libraries are linked from the stubs. `method scotch` cases
#     (tests/test_al.py::test_parallel) cannot decompose here; use `simple`.
#     The dummy Pstream must NOT be on the path or MPI runs abort.
source /etc/profile.d/modules.sh
module load openfoam/v2506_openmpi-4.1.4_gnu >/dev/null 2>&1
export WM_ARCH=linux64 WM_COMPILER=Gcc WM_COMPILE_OPTION=Opt WM_PRECISION_OPTION=DP WM_LABEL_SIZE=64
export WM_OPTIONS=linux64GccDPInt64Opt
export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
export FOAM_USER_APPBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/bin
_foam_dummy="${TMPDIR:-/tmp}/foam-dummy-decomp-${USER}"
mkdir -p "$_foam_dummy"
for _lib in libmetisDecomp libkahipDecomp libscotchDecomp libptscotchDecomp; do
    ln -sf "$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/dummy/$_lib.so" "$_foam_dummy/$_lib.so"
done
export LIBRARY_PATH=/scratch/app/gcc/15.2.0/lib64
export LD_LIBRARY_PATH=$_foam_dummy:/scratch/app/gcc/15.2.0/lib64:/scratch/app/gcc/14.2.0/lib64:$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$LD_LIBRARY_PATH
export PATH=$WM_PROJECT_DIR/platforms/$WM_OPTIONS/bin:$FOAM_USER_APPBIN:$PATH
unset _foam_dummy _lib
