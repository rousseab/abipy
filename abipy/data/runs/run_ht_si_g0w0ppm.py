#!/usr/bin/env python
"""G0W0 corrections with the HT interface."""
from __future__ import division, print_function, unicode_literals

import sys
import os
import abipy.data as abidata  

from pymatgen.io.abinitio.calculations import g0w0_with_ppmodel_work
from abipy import abilab


def build_flow(options):
    structure = abilab.Structure.from_file(abidata.cif_file("si.cif"))
    pseudos = abidata.pseudos("14si.pspnc")

    # Working directory (default is the name of the script with '.py' removed and "run_" replaced by "flow_")
    workdir = options.workdir
    if not options.workdir:
        workdir = os.path.basename(__file__).replace(".py", "").replace("run_","flow_") 

    # Initialize the flow.
    flow = abilab.Flow(workdir, manager=options.manager) 

    scf_kppa = 10
    nscf_nband = 10
    #nscf_ngkpt = [4,4,4]
    #nscf_shiftk = [0.0, 0.0, 0.0]
    ecut, ecuteps, ecutsigx = 4, 2, 3
    #scr_nband = 50
    #sigma_nband = 50

    extra_abivars = dict(
        ecut=ecut, 
        istwfk="*1",
    )

    work = g0w0_with_ppmodel_work(structure, pseudos, scf_kppa, nscf_nband, ecuteps, ecutsigx,
                                  accuracy="normal", spin_mode="unpolarized", smearing=None, 
                                  ppmodel="godby", charge=0.0, inclvkb=2, sigma_nband=None, gw_qprange=1,
                                  scr_nband=None, **extra_abivars)
    
    flow.register_work(work)
    return flow
    

@abilab.flow_main
def main(options):
    flow = build_flow(options)
    flow.build_and_pickle_dump()
    return flow


if __name__ == "__main__":
    sys.exit(main())
