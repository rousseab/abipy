"""
Integration tests for flows (require pytest, ABINIT and a properly configured environment)
"""
from __future__ import print_function, division, unicode_literals

import pytest
import abipy.data as abidata
import abipy.abilab as abilab

from pymatgen.io.abinitio.calculations import bandstructure_work
from abipy.core.testing import has_abinit, has_matplotlib

# Tests in this module require abinit >= 7.9.0
#pytestmark = pytest.mark.skipif(not has_abinit("7.9.0"), reason="Requires abinit >= 7.9.0")


def make_scf_nscf_inputs(tvars, pp_paths, nstep=50):
    """
    Returns two input files: GS run and NSCF on a high symmetry k-mesh
    """
    multi = abilab.MultiDataset(structure=abidata.cif_file("si.cif"),
                                pseudos=abidata.pseudos(pp_paths), ndtset=2)

    nval = multi[0].num_valence_electrons
    assert all(inp.num_valence_electrons == 8 for inp in multi)

    # Global variables
    ecut = 4
    global_vars = dict(ecut=ecut,
                       nband=int(nval/2),
                       nstep=nstep,
                       paral_kgb=tvars.paral_kgb)

    if multi.ispaw:
        global_vars.update(pawecutdg=2*ecut)

    multi.set_vars(global_vars)

    # Dataset 1 (GS run)
    multi[0].set_kmesh(ngkpt=[4, 4, 4], shiftk=[0, 0, 0])
    multi[0].set_vars(tolvrs=1e-4)

    # Dataset 2 (NSCF run)
    kptbounds = [
        [0.5, 0.0, 0.0],  # L point
        [0.0, 0.0, 0.0],  # Gamma point
        [0.0, 0.5, 0.5],  # X point
    ]

    multi[1].set_kpath(ndivsm=2, kptbounds=kptbounds)
    multi[1].set_vars(tolwfr=1e-6)
    
    # Generate two input files for the GS and the NSCF run.
    scf_input, nscf_input = multi.split_datasets()

    return scf_input, nscf_input


def itest_unconverged_scf(fwp, tvars):
    """Test the treatment of unconverged GS calculations."""
    print("tvars:\n %s" % str(tvars))

    # Build the SCF and the NSCF input (note nstep to have an unconverged run)
    scf_input, nscf_input = make_scf_nscf_inputs(tvars, pp_paths="14si.pspnc", nstep=1)

    # Build the flow and create the database.
    flow = abilab.bandstructure_flow(fwp.workdir, scf_input, nscf_input, manager=fwp.manager)
    flow.allocate()

    # Use smart-io
    flow.use_smartio()

    flow.build_and_pickle_dump()

    t0 = flow[0][0]
    t1 = flow[0][1]

    assert t0.uses_paral_kgb(tvars.paral_kgb)
    assert t1.uses_paral_kgb(tvars.paral_kgb)

    # This run should not converge.
    t0.start_and_wait()
    t0.check_status()
    assert t0.status == t0.S_UNCONVERGED
    # Unconverged with smart-io --> WFK must be there
    assert t0.outdir.has_abiext("WFK")
    #assert 0

    # Remove nstep from the input so that we use the default value.
    # Then restart the GS task and test that GS is OK.
    assert not t1.can_run
    t0.input.pop("nstep")
    assert t0.num_restarts == 0
    t0.restart()
    t0.wait()
    assert t0.num_restarts == 1
    t0.check_status()
    assert t0.status == t1.S_OK

    # Converged with smart-io --> WFK is not written
    assert not t0.outdir.has_abiext("WFK")

    # Now we can start the NSCF step
    assert t1.can_run
    t1.start_and_wait()
    t1.check_status()
    assert t1.status == t0.S_UNCONVERGED

    assert not flow.all_ok

    # Restart (same trick as the one used for the GS run)
    t1.input.pop("nstep")
    assert t1.num_restarts == 0
    assert t1.restart()
    t1.wait()
    assert t1.num_restarts == 1
    assert t1.status == t1.S_DONE
    t1.check_status()
    assert t1.status == t1.S_OK

    flow.show_status()
    assert flow.all_ok

    # Test inspect methods
    if has_matplotlib():
        t0.inspect(show=False)

    # Test get_results
    t0.get_results()
    t1.get_results()

    # Build tarball file.
    tarfile = flow.make_tarfile()

    #assert flow.validate_json_schema()

    # Test reset_from_scratch
    t0.reset_from_scratch()
    assert t0.status == t0.S_READY
    # Datetime counters shouls be set to None
    dt = t0.datetimes
    assert (dt.submission, dt.start, dt.end) == (None, None, None)

    t0.start_and_wait()
    t0.reset_from_scratch()

    # Datetime counters shouls be set to None
    dt = t0.datetimes
    assert (dt.submission, dt.start, dt.end) == (None, None, None)

    #assert 0


def itest_bandstructure_flow(fwp, tvars):
    """
    Test band-structure flow with one dependency: SCF -> NSCF.
    """
    print("tvars:\n %s" % str(tvars))

    # Get the SCF and the NSCF input.
    scf_input, nscf_input = make_scf_nscf_inputs(tvars, pp_paths="14si.pspnc")

    # Build the flow and create the database.
    flow = abilab.bandstructure_flow(fwp.workdir, scf_input, nscf_input, manager=fwp.manager)
    flow.build_and_pickle_dump()

    t0 = flow[0][0]
    t1 = flow[0][1]

    # Test initialization status, task properties and links (t1 requires t0)
    assert t0.status == t0.S_INIT
    assert t1.status == t1.S_INIT
    assert t0.can_run
    assert not t1.can_run
    assert t1.depends_on(t0)
    assert not t1.depends_on(t1)
    assert t0.isnc
    assert not t0.ispaw

    # Flow properties and methods
    assert flow.num_tasks == 2
    assert not flow.all_ok
    assert flow.ncores_reserved == 0
    assert flow.ncores_allocated == 0
    assert flow.ncores_used == 0
    flow.check_dependencies()
    flow.show_status()
    flow.show_receivers()

    # Run t0, and check status
    assert t0.returncode == 0
    t0.start_and_wait()
    assert t0.returncode == 0
    assert t0.status == t0.S_DONE
    t0.check_status()
    assert t0.status == t0.S_OK
    assert t1.can_run

    # Cannot start t0 twice...
    with pytest.raises(t0.Error):
        t0.start()

    # But we can restart it.
    fired = t0.restart()
    assert fired
    t0.wait()
    assert t0.num_restarts == 1
    assert t0.status == t0.S_DONE
    t0.check_status()
    assert t0.status == t0.S_OK
    assert not t0.can_run

    # Now we can run t1.
    t1.start_and_wait()
    assert t1.status == t0.S_DONE
    t1.check_status()
    assert t1.status == t1.S_OK
    assert not t1.can_run

    # This one does not work yet
    #fired = t1.restart()
    #atrue(fired)
    #t1.wait()
    #aequal(t1.num_restarts, 1)
    #aequal(t1.status, t1.S_DONE)
    #t1.check_status()
    #aequal(t1.status, t1.S_OK)
    #afalse(t1.can_run)

    flow.show_status()
    assert flow.all_ok
    assert all(work.finalized for work in flow)

    for task in flow.iflat_tasks():
        assert len(task.outdir.list_filepaths(wildcard="*GSR.nc")) == 1

    # Test GSR robot
    with abilab.abirobot(flow, "GSR") as robot:
        table = robot.get_dataframe()
        assert table is not None
        print(table)

    #assert flow.validate_json_schema()
    #assert 0


def itest_bandstructure_schedflow(fwp, tvars):
    """
    Run a bandstructure flow with the scheduler.
    """
    print("tvars:\n %s" % str(tvars))

    # Get the SCF and the NSCF input.
    scf_input, nscf_input = make_scf_nscf_inputs(tvars, pp_paths="Si.GGA_PBE-JTH-paw.xml")

    # Build the flow and create the database.
    flow = abilab.bandstructure_flow(fwp.workdir, scf_input, nscf_input, manager=fwp.manager)

    # Will remove output files (WFK)
    flow.set_garbage_collector()
    flow.build_and_pickle_dump()

    fwp.scheduler.add_flow(flow)
    print(fwp.scheduler)
    # scheduler cannot handle more than one flow.
    with pytest.raises(fwp.scheduler.Error):
        fwp.scheduler.add_flow(flow)

    assert fwp.scheduler.start() == 0
    assert not fwp.scheduler.exceptions
    assert fwp.scheduler.nlaunch == 2

    flow.show_status()
    assert flow.all_ok
    assert all(work.finalized for work in flow)

    # The WFK files should have been removed because we called set_garbage_collector
    for task in flow[0]:
        assert not task.outdir.has_abiext("WFK")

    # Test if GSR files are produced and are readable.
    for i, task in enumerate(flow[0]):
        with task.open_gsr() as gsr:
            print(gsr)
            assert gsr.nsppol == 1
            #assert gsr.structure == structure
            ebands = gsr.ebands

            # TODO: This does not work yet because GSR files do not contain
            # enough info to understand if we have a path or a mesh.
            #if i == 2:
                # Bandstructure case
                #assert ebands.has_bzpath
                #with pytest.raises(ebands.Error):
                #    ebands.get_edos()

            #if i == 3:
            #    # DOS case
            #    assert ebands.has_bzmesh
            #    gsr.bands.get_edos()

    #assert flow.validate_json_schema()
    #assert 0


def itest_htc_bandstructure(fwp, tvars):
    """Test band-structure calculations done with the HTC interface."""
    structure = abilab.Structure.from_file(abidata.cif_file("si.cif"))

    scf_kppa = 20
    nscf_nband = 6
    ndivsm = 5
    dos_kppa = 40
    # TODO: Add this options because I don't like the kppa approach
    # I had to use it because it was the approach used in VaspIO
    #dos_ngkpt = [4,4,4]
    #dos_shiftk = [0.1, 0.2, 0.3]

    extra_abivars = dict(ecut=2, paral_kgb=tvars.paral_kgb)

    # Initialize the flow.
    flow = abilab.Flow(workdir=fwp.workdir, manager=fwp.manager)

    work = bandstructure_work(structure, abidata.pseudos("14si.pspnc"), scf_kppa, nscf_nband, ndivsm,
                              spin_mode="unpolarized", smearing=None, dos_kppa=dos_kppa, **extra_abivars)

    flow.register_work(work)
    flow.allocate()
    flow.build_and_pickle_dump()

    fwp.scheduler.add_flow(flow)
    assert fwp.scheduler.start() == 0
    assert not fwp.scheduler.exceptions
    assert fwp.scheduler.nlaunch == 3

    flow.show_status()
    assert flow.all_ok
    assert all(work.finalized for work in flow)

    # Test if GSR files are produced and are readable.
    for i, task in enumerate(work):
        with task.open_gsr() as gsr:
            print(gsr)
            assert gsr.nsppol == 1
            #assert gsr.structure == structure
            ebands = gsr.ebands

            # TODO: This does not work yet because GSR files do not contain
            # enough info to understand if we have a path or a mesh.
            #if i == 2:
                # Bandstructure case
                #assert ebands.has_bzpath
                #with pytest.raises(ebands.Error):
                #    ebands.get_edos()

            if i == 3:
                # DOS case
                assert ebands.has_bzmesh
                gsr.bands.get_edos()

    #assert flow.validate_json_schema()
