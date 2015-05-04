#!/usr/bin/env python
"""
Relaxation of atomic positions with unit cell parameters fixed.
"""
from __future__ import division, print_function

import sys
import os
import abipy.data as abidata
import abipy.abilab as abilab
import abipy.fworks.fw_workflows as fw_workflows


def make_ion_ioncell_inputs():
    cif_file = abidata.cif_file("si.cif")
    structure = abilab.Structure.from_file(cif_file)

    # Perturb the structure (random perturbation of 0.1 Angstrom)
    structure.perturb(distance=0.1)

    pseudos = abidata.pseudos("14si.pspnc")

    global_vars = dict(
        ecut=4,
        ngkpt=[4,4,4],
        shiftk=[0,0,0],
        nshiftk=1,
        chksymbreak=0,
        paral_kgb=0,
    )

    inp = abilab.AbiInput(pseudos=pseudos, ndtset=2)
    inp.set_structure(structure)

    # Global variables
    inp.set_vars(**global_vars)

    # Dataset 1 (Atom Relaxation)
    inp[1].set_vars(
        optcell=0,
        ionmov=2,
        tolrff=0.02,
        tolmxf=5.0e-5,
        ntime=50,
        #ntime=5, To test the restart
        dilatmx=1.1, # FIXME: abinit crashes if I don't use this
    )

    # Dataset 2 (Atom + Cell Relaxation)
    inp[2].set_vars(
        optcell=1,
        ionmov=2,
        ecutsm=0.5,
        dilatmx=1.1,
        tolrff=0.02,
        tolmxf=5.0e-5,
        strfact=100,
        ntime=50,
        #ntime=5, To test the restart
        )

    ion_inp, ioncell_inp = inp.split_datasets()
    return ion_inp, ioncell_inp


def build_flow():
    # Working directory (default is the name of the script with '.py' removed and "run_" replaced by "flow_")
    workdir = os.path.basename(__file__).replace(".py", "").replace("run_","flow_")

    # Instantiate the TaskManager.
    manager = abilab.TaskManager.from_user_config()

    # Create a relaxation workflow
    ion_inp, ioncell_inp = make_ion_ioncell_inputs()
    flow=fw_workflows.RelaxFWWorkflow(ion_inp, ioncell_inp, workdir, manager)

    return flow


def main():
    flow = build_flow()
    return flow.add_to_db()


if __name__ == "__main__":
    sys.exit(main())

