#!/usr/bin/env python
"""Flow for computing the band structure of silicon."""
from __future__ import division, print_function, unicode_literals

import sys
import os
import abipy.data as abidata  
import abipy.abilab as abilab


def make_scf_nscf_inputs(paral_kgb=1):
    """Returns two input files: GS run and NSCF on a high symmetry k-mesh."""
    pseudos = abidata.pseudos("14si.pspnc")

    inp = abilab.AbiInput(pseudos=pseudos, ndtset=2)
    structure = inp.set_structure(abidata.cif_file("si.cif"))

    # Global variables
    ecut = 6
    global_vars = dict(ecut=ecut,
                       nband=8,
                       nstep=15,
                       paral_kgb=paral_kgb,
                    )

    if inp.ispaw:
        global_vars.update(pawecutdg=2*ecut)

    inp.set_vars(**global_vars)

    # Dataset 1 (GS run)
    inp[1].set_kmesh(ngkpt=[8,8,8], shiftk=[0,0,0])
    inp[1].set_vars(tolvrs=1e-6)

    # Dataset 2 (NSCF run)
    kptbounds = [
        [0.5, 0.0, 0.0], # L point
        [0.0, 0.0, 0.0], # Gamma point
        [0.0, 0.5, 0.5], # X point
    ]

    inp[2].set_kpath(ndivsm=6, kptbounds=kptbounds)
    inp[2].set_vars(tolwfr=1e-12)
    
    # Generate two input files for the GS and the NSCF run 
    scf_input, nscf_input = inp.split_datasets()

    return scf_input, nscf_input


def build_flow(options):
    # Working directory (default is the name of the script with '.py' removed and "run_" replaced by "flow_")
    workdir = options.workdir
    if not options.workdir:
        workdir = os.path.basename(__file__).replace(".py", "").replace("run_","flow_") 

    # Instantiate the TaskManager.
    manager = abilab.TaskManager.from_user_config() if not options.manager else \
              abilab.TaskManager.from_file(options.manager)

    # Get the SCF and the NSCF input.
    scf_input, nscf_input = make_scf_nscf_inputs()

    # Build the flow.
    flow = abilab.Flow(workdir, manager=manager)

    # Create a Work, all tasks in work will read the file f
    # Note that the file must exist when the work is created
    # Use the standard approach based on tasks and works if
    # there's a node who needs a file produced in the future.
    work = abilab.Work()
    denfile = abidata.ref_file("si_DEN-etsf.nc")
    work.register(nscf_input, deps={denfile: "DEN"})
    flow.register_work(work)

    return flow.allocate()
    

@abilab.flow_main
def main(options):
    flow = build_flow(options)
    return flow.build_and_pickle_dump()


if __name__ == "__main__":
    sys.exit(main())
