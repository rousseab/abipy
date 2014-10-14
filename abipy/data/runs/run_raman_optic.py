#!/usr/bin/env python
"""
This script shows how to perform a RAMAN calculation with excitonic effects 
included with the BSE formalism.
"""
from __future__ import division, print_function

import sys 
import os
import numpy as np

import abipy.abilab as abilab
import abipy.data as data  
#from pymatgen.io.abinitio.tasks import TaskPolicy

optic_input = """\
0.002         ! Value of the smearing factor, in Hartree
0.0003  0.3   ! Difference between frequency values (in Hartree), and maximum frequency ( 1 Ha is about 27.211 eV)
0.000         ! Scissor shift if needed, in Hartree
0.002         ! Tolerance on closeness of singularities (in Hartree)
6             ! Number of components of linear optic tensor to be computed
11 12 13 22 23 33     ! Linear coefficients to be computed (x=1, y=2, z=3)
0             ! Number of components of nonlinear optic tensor to be computed
      ! Non-linear coefficients to be computed
"""


global_vars = dict(
    istwfk="*1",
    paral_kgb=0,
    ecut=15,
    nstep=500,
    spinat=[[0.0000000000E+00,  0.0000000000E+00,  3.5716762600E+00],
            [0.0000000000E+00,  0.0000000000E+00, -3.5716762600E+00],
            [0.0000000000E+00,  0.0000000000E+00,  0.0000000000E+00],
            [0.0000000000E+00,  0.0000000000E+00,  0.0000000000E+00],
            [0.0000000000E+00,  0.0000000000E+00,  0.0000000000E+00],
            [0.0000000000E+00,  0.0000000000E+00,  0.0000000000E+00],
            [0.0000000000E+00,  0.0000000000E+00,  0.0000000000E+00],
            [0.0000000000E+00,  0.0000000000E+00,  0.0000000000E+00],
            [0.0000000000E+00,  0.0000000000E+00,  0.0000000000E+00],
            [0.0000000000E+00,  0.0000000000E+00,  0.0000000000E+00]],
    nsppol=2,
    nspden=2,
    diemac=5,
    diemix=0.6,
    ixc=7,
    chksymbreak=0,
    #accesswff=3
)

def raman_flow():

    # Get the unperturbed structure.
    pseudos=data.pseudos("14si.pspnc")

    base_structure = data.structure_from_ucell("Si")

    ngkpt = [6,6,6]

    etas = [-.002,-.001, 0, +.001, +.002]
    ph_displ = np.reshape(np.zeros(3*len(base_structure)), (-1,3))
    ph_displ[0,:] = [+1, 0, 0]
    ph_displ[1,:] = [-1, 0, 0]

    # Build new structures by displacing atoms according to the phonon displacement
    # ph_displ (in cartesian coordinates). The Displacement is normalized so that 
    # the maximum atomic diplacement is 1 Angstrom and then multiplied by eta.
    modifier = abilab.StructureModifier(base_structure)

    displaced_structures = modifier.displace(ph_displ, etas, frac_coords=False)

    # Initialize flow. Each workflow in the flow defines a complete BSE calculation for given eta.
    workdir = os.path.join(os.path.dirname(__file__), base_structure.formula.replace(" ","") + "_RAMAN")

    manager = abilab.TaskManager.from_user_config()
    shell_manager = manager.to_shell_manager(mpi_ncpus=1)
    ddk_manager = manager.deepcopy()

    flow = abilab.AbinitFlow(workdir, manager)

    # Generate the different shifts to average
    ndiv = 1
    shift1D = np.arange(1,2*ndiv+1,2)/(2*ndiv)
    all_shifts = [[x,y,z] for x in shift1D for y in shift1D for z in shift1D]

    for structure, eta in zip(displaced_structures, etas):
        for ishift,shift in enumerate(all_shifts):
            flow.register_work(raman_workflow(structure, pseudos, ngkpt, shift, ddk_manager, shell_manager),workdir="eta_"+str(eta)+"shift_"+str(ishift))

    return flow.allocate()


def raman_workflow(structure, pseudos, ngkpt, shiftk, ddk_manager, shell_manager):
    # Generate 3 different input files for computing optical properties with BSE.

    inp = abilab.AbiInput(pseudos=pseudos, ndtset=5)

    inp.set_structure(structure)
    inp.set_variables(**global_vars)
    inp.set_kmesh(ngkpt=ngkpt, shiftk=shiftk)

    # GS run
    inp[1].set_variables(
        tolvrs=1e+8,
        nband=59,
    )

    # NSCF run
    inp[2].set_variables(
        iscf=-2,
       nband=100,
       kptopt=1,
       tolwfr=1.e+12,
    )
    
    # DDK along 3 directions
    # Third dataset : ddk response function along axis 1
    # Fourth dataset : ddk response function along axis 2
    # Fifth dataset : ddk response function along axis 3
    for dir in range(3):
        rfdir = 3 * [0]
        rfdir[dir] = 1

        inp[3+dir].set_variables(
           iscf=-3,
	   nband=100,
          nstep=1,
          nline=0,
          prtwf=3,
         kptopt=1,
           nqpt=1,
           qpt=[0.0, 0.0, 0.0],
          rfdir=rfdir,
         rfelfd=2,
         tolwfr=1.e+12,
        )

    scf_inp, nscf_inp, ddk1, ddk2, ddk3 = inp.split_datasets()
    ddk_inputs = [ddk1, ddk2, ddk3]

    workflow = abilab.Workflow()
    scf_t = workflow.register_scf_task(scf_inp)
    nscf_t = workflow.register_nscf_task(nscf_inp, deps={scf_t: "DEN"})

    ddk_nodes = []
    for inp in ddk_inputs:
        ddk_t = workflow.register_ddk_task(inp, deps={nscf_t: "WFK"})
        ddk_t.set_manager(ddk_manager)
        ddk_nodes.append(ddk_t)

    optic_t = abilab.OpticTask(optic_input, nscf_node=nscf_t, ddk_nodes=ddk_nodes, manager=shell_manager)

    workflow.register(optic_t)

    return workflow


def main():
    # Define the flow, build files and dirs 
    # and save the object in cpickle format.
    flow = raman_flow()
    return flow.build_and_pickle_dump()


if __name__ == "__main__":
    sys.exit(main())
