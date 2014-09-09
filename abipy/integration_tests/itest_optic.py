"""Optical spectra with Optic."""
from __future__ import print_function, division

import pytest
import abipy.data as abidata
import abipy.abilab as abilab

from abipy.core.testing import has_abinit

# Tests in this module require abinit >= 7.9.0
pytestmark = pytest.mark.skipif(not has_abinit("7.9.0"), reason="Requires abinit >= 7.9.0")


def make_inputs(tvars):
    """Constrcut the input files."""
    structure = abidata.structure_from_ucell("GaAs")

    inp = abilab.AbiInput(pseudos=abidata.pseudos("31ga.pspnc", "33as.pspnc"), ndtset=5)
    inp.set_structure(structure)

    # Global variables
    kmesh = dict(ngkpt=[4, 4, 4],
                 nshiftk=4,
                 shiftk=[[0.5, 0.5, 0.5],
                         [0.5, 0.0, 0.0],
                         [0.0, 0.5, 0.0],
                         [0.0, 0.0, 0.5]])

    global_vars = dict(ecut=2,
                       paral_kgb=tvars.paral_kgb)

    global_vars.update(kmesh)

    inp.set_variables(**global_vars)

    # Dataset 1 (GS run)
    inp[1].set_variables(
        tolvrs=1e-6,
        nband=4)

    # NSCF run with large number of bands, and points in the the full BZ
    inp[2].set_variables(
        iscf=-2,
        nband=20,
        nstep=25,
        kptopt=1,
        tolwfr=1.e-8)
        #kptopt=3)

    # Fourth dataset: ddk response function along axis 1
    # Fifth dataset: ddk response function along axis 2
    # Sixth dataset: ddk response function along axis 3
    for idir in range(3):
        rfdir = 3 * [0]
        rfdir[idir] = 1

        inp[3+idir].set_variables(
            iscf=-3,
            nband=20,
            nstep=1,
            nline=0,
            prtwf=3,
            kptopt=3,
            nqpt=1,
            qpt=[0.0, 0.0, 0.0],
            rfdir=rfdir,
            rfelfd=2,
            tolwfr=1.e-9,
        )

    # scf_inp, nscf_inp, ddk1, ddk2, ddk3
    return inp.split_datasets()


optic_input = """\
0.002         ! Value of the smearing factor, in Hartree
0.0003  0.3   ! Difference between frequency values (in Hartree), and maximum frequency ( 1 Ha is about 27.211 eV)
0.000         ! Scissor shift if needed, in Hartree
0.002         ! Tolerance on closeness of singularities (in Hartree)
1             ! Number of components of linear optic tensor to be computed
11            ! Linear coefficients to be computed (x=1, y=2, z=3)
2             ! Number of components of nonlinear optic tensor to be computed
123 222       ! Non-linear coefficients to be computed
"""


def itest_optic_flow(fwp, tvars):
    """Test optic calculations."""
    if tvars.paral_kgb == 1:
        pytest.xfail("Optic flow with paral_kgb==1 is expected to fail (implementation problem)")

    scf_inp, nscf_inp, ddk1, ddk2, ddk3 = make_inputs(tvars)

    flow = abilab.AbinitFlow(fwp.workdir, fwp.manager)

    bands_work = abilab.BandStructureWorkflow(scf_inp, nscf_inp)
    flow.register_work(bands_work)

    # workflow with DDK tasks.
    ddk_work = abilab.Workflow()
    for inp in [ddk1, ddk2, ddk3]:
        ddk_work.register(inp, deps={bands_work.nscf_task: "WFK"}, task_class=abilab.DdkTask)

    flow.register_work(ddk_work)
    flow.allocate()
    flow.build_and_pickle_dump()

    # Run the tasks
    for task in flow.iflat_tasks():
        task.start_and_wait()
        assert task.status == task.S_DONE

    flow.check_status()
    assert flow.all_ok

    # Optic does not support MPI with ncpus > 1 hence we have to construct a manager with mpi_ncpus==1
    shell_manager = fwp.manager.to_shell_manager(mpi_ncpus=1)

    # Build optic task and register it
    optic_task1 = abilab.OpticTask(optic_input, nscf_node=bands_work.nscf_task, ddk_nodes=ddk_work,
                                   manager=shell_manager)

    flow.register_task(optic_task1)
    flow.allocate()
    flow.build_and_pickle_dump()

    optic_task1.start_and_wait()
    assert optic_task1.status == optic_task1.S_DONE

    # Now we do a similar calculation but the dependencies are represented by
    # strings with the path to the input files instead of task objects.
    ddk_nodes = [task.outdir.has_abiext("1WF") for task in ddk_work]
    print("ddk_nodes:", ddk_nodes)
    assert all(ddk_nodes)

    #nscf_node = bands_work.nscf_task
    nscf_node = bands_work.nscf_task.outdir.has_abiext("WFK")
    assert nscf_node

    # This does not work yet
    optic_task2 = abilab.OpticTask(optic_input, nscf_node=nscf_node, ddk_nodes=ddk_nodes)
    flow.register_task(optic_task2)
    flow.allocate()
    flow.build_and_pickle_dump()
    assert len(flow) == 4

    optic_task2.start_and_wait()
    assert optic_task2.status == optic_task2.S_DONE

    flow.check_status()
    flow.show_status()
    assert flow.all_ok
    assert all(work.finalized for work in flow)

