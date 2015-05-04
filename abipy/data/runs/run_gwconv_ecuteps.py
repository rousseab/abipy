#!/usr/bin/env python
"""G0W0 convergence study wrt ecuteps and the number of bands in W."""
from __future__ import division, print_function, unicode_literals

import sys
import os
import numpy as np

import abipy.abilab as abilab
import abipy.data as abidata

def make_inputs(paral_kgb=1):
    """
    Returns a tuple of 4 input files for SCF, NSCF, SCR, SIGMA calculations.
    These files are then used as templates for the convergence study
    wrt ecuteps and the number of bands in W.
    """
    multi = abilab.MultiDataset(abidata.structure_from_ucell("SiC"), 
                                pseudos=abidata.pseudos("14si.pspnc", "6c.pspnc"), ndtset=4)

    ecut = 12
    global_vars = dict(
        ecut=ecut,
        istwfk="*1",
        paral_kgb=paral_kgb,
        gwpara=2
    )

    ecuteps = 4
    ngkpt = [4, 4, 4]
    shiftk = [0, 0, 0]

    multi.set_vars(global_vars)
    multi.set_kmesh(ngkpt=ngkpt, shiftk=shiftk)

    # SCF
    multi[0].set_vars(
        nband=10,
        tolvrs=1.e-8,
    )

    # NSCF
    multi[1].set_vars(
        nband=25,
        tolwfr=1.e-8,
        iscf=-2
    )

    # SCR
    multi[2].set_vars(
        optdriver=3,
        ecutwfn=ecut,
        nband=20,
        symchi=1,
        inclvkb=0,
        ecuteps=ecuteps,
    )
        
    # SIGMA
    multi[3].set_vars(
        optdriver=4,
        nband=20,
        ecutwfn=ecut,
        ecutsigx=ecut,
        #ecutsigx=(4*ecut), ! This is problematic
        symsigma=1,
        ecuteps=ecuteps,
        )

    multi[3].set_kptgw(kptgw=[[0,0,0], [0.5, 0, 0]], bdgw=[1, 8])

    return multi.split_datasets()


def build_flow(options):
    # Working directory (default is the name of the script with '.py' removed and "run_" replaced by "flow_")
    workdir = options.workdir
    if not options.workdir:
        workdir = os.path.basename(__file__).replace(".py", "").replace("run_","flow_") 

    # Get our templates
    scf_inp, nscf_inp, scr_inp, sig_inp = make_inputs()
    
    ecuteps_list = np.arange(2, 8, 2)
    max_ecuteps = max(ecuteps_list)

    flow = abilab.Flow(workdir=workdir, manager=options.manager)

    # Band structure work to produce the WFK file
    bands = abilab.BandStructureWork(scf_inp, nscf_inp)
    flow.register_work(bands)

    # Build a work made of two SCR runs with different value of nband
    # Use max_ecuteps for the dielectric matrix (sigma tasks will 
    # read a submatrix when we test the convergence wrt to ecuteps.
    scr_work = abilab.Work()

    for inp in abilab.input_gen(scr_inp, nband=[10, 15]):
        inp.set_vars(ecuteps=max_ecuteps)
        scr_work.register_scr_task(inp, deps={bands.nscf_task: "WFK"})

    flow.register_work(scr_work)

    # Do a convergence study wrt ecuteps, each work is connected to a
    # different SCR file computed with a different value of nband.

    # Build a list of sigma inputs with different ecuteps
    sigma_inputs = list(abilab.input_gen(sig_inp, ecuteps=ecuteps_list))

    for scr_task in scr_work:
        sigma_conv = abilab.SigmaConvWork(wfk_node=bands.nscf_task, scr_node=scr_task, sigma_inputs=sigma_inputs)
        flow.register_work(sigma_conv)

    return flow


@abilab.flow_main
def main(options):
    flow = build_flow(options)
    flow.build_and_pickle_dump()
    return flow


if __name__=="__main__":
    sys.exit(main())

