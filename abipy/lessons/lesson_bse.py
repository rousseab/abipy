#!/usr/bin/env python
from __future__ import division, print_function

import os
import numpy as np
import abipy.abilab as abilab 
import abipy.data as abidata


def make_inputs(ngkpt=(4,4,4), ecut=8, ecuteps=2):
    """
    """
    inp = abilab.AbiInput(pseudos=abidata.pseudos("14si.pspnc"), ndtset=3)
    #inp.set_structure(abidata.cif_file("si.cif"))
    inp.set_structure(abidata.structure_from_ucell("Si"))

    inp.set_variables(
        ecut=ecut, 
        nband=8,
        istwfk="*1",
        diemac=12.0,
        paral_kgb=1,
    )

    inp[1].set_variables(tolvrs=1e-8)
    #inp[1].set_autokmesh(nksmall=min(ngkpt))
    inp[1].set_kmesh(ngkpt=ngkpt, shiftk=(0, 0, 0))

    inp[2].set_variables(
        iscf=-2,
        nband=15,
        tolwfr=1e-8,
        chksymbreak=0,               # To skip the check on the k-mesh.
    )

    # This shift breaks the symmetry of the k-mesh.
    inp[2].set_kmesh(ngkpt=ngkpt, shiftk=(0.11,0.21,0.31))

    # BSE run with Haydock iterative method (only resonant + W + v)
    inp[3].set_variables(
        optdriver=99,               # BS calculation
        chksymbreak=0,              # To skip the check on the k-mesh.
        bs_calctype=1,              # L0 is contstructed with KS orbitals and energies.
        soenergy="0.8 eV",          # Scissors operator used to correct the KS band structure.
        bs_exchange_term=1,         # Exchange term included.
        bs_coulomb_term=21,         # Coulomb term with model dielectric function.
        mdf_epsinf=12.0,            # Parameter for the model dielectric function.
        bs_coupling=0,              # Tamm-Dancoff approximation.
        bs_loband=3,
        nband=6,
        #bs_freq_mesh=0 6 0.02 eV,  # Frequency mesh.
        bs_algorithm=2,             # Haydock method.
        #bs_haydock_niter=200       # Max number of iterations for the Haydock method.
        #bs_haydock_tol=0.05 0,     # Tolerance for the iterative method.
        zcut="0.15 eV",             # complex shift to avoid divergences in the continued fraction.
        ecutwfn=ecut,               # Cutoff for the wavefunction.
        ecuteps=ecuteps,            # Cutoff for W and /bare v used to calculate the BS matrix elements.
        inclvkb=2,                  # The commutator for the optical limit is correctly evaluated.
    )

    inp[3].set_kmesh(ngkpt=ngkpt, shiftk=(0.11,0.21,0.31))

    scf_input, nscf_input, bse_input = inp.split_datasets()
    return scf_input, nscf_input, bse_input


def eh_convergence_study():
    """
    """
    scf_input, nscf_input, bse_template = make_inputs()
    workdir = "flow_bse_bands"

    if not os.path.exists(workdir):
        print("Calling the scheduler")
        bands_flow = abilab.bandstructure_flow(workdir, scf_input, nscf_input)
        bands_flow.make_scheduler().start()
    else:
        print("Initializing flow from %s" % workdir)
        bands_flow = abilab.Flow.pickle_load(workdir)

    if not bands_flow.all_ok:
        raise RuntimeError("bands_flow must have reached all_ok")

    wfk_file = bands_flow.nscf_task.outdir.has_abiext("WFK")
    if not wfk_file:
        raise RuntimeError("WFK file does not exist")

    work = abilab.Work()
    #for inp in bse_template.generate(ecuteps=range(2, 4, 1)):
    for inp in bse_template.generate(zcut=["0.1 eV", "0.2 eV", "0.3 eV"]):
        work.register_bse_task(inp, deps={wfk_file: "WFK"})

    flow = abilab.Flow(workdir="flow_bse_ecuteps")
    flow.register_work(work)
    flow.allocate()
    flow.build()

    #flow.make_scheduler().start()

    import matplotlib.pyplot as plt
    import pandas as pd

    with abilab.abirobot(flow, "MDF") as robot:
        frame = robot.get_dataframe()
        #print(frame)
        #plotter = robot.get_mdf_plotter()
        #plotter.plot()

        robot.plot_conv_mdf(hue="broad")

        #grouped = frame.groupby("broad")
        #fig, ax_list = plt.subplots(nrows=len(grouped), ncols=1, sharex=True, sharey=True, squeeze=True)

        #for i, (zcut, group) in enumerate(grouped):
        #    print(group)
        #    mdfs = group["exc_mdf"] 
        #    ax = ax_list[i]
        #    ax.set_title("zcut %s" % zcut)
        #    for mdf in mdfs:
        #        mdf.plot_ax(ax)
        #plt.show()

if __name__ == "__main__":
    eh_convergence_study()
