#!/usr/bin/env python
#
# This example shows how to compute and plot several
# gaussian DOS by varying the broadening parameters.
import abipy.data as abidata
from abipy.abilab import abiopen, ElectronDosPlotter

# Open the wavefunction file computed with a homogeneous sampling of the BZ 
# and extract the band structure on the k-mesh.
with abiopen(abidata.ref_file("si_scf_WFK-etsf.nc")) as gs_wfk:
    gs_bands = gs_wfk.ebands

# Compute the DOS with the Gaussian method.
# Plot bands and DOS.
widths = [0.1, 0.2, 0.3]
step = 0.1

plotter = ElectronDosPlotter()

for width in widths:
   edos = gs_bands.get_edos(method="gaussian", step=step, width=width)
   label="$\sigma = %s$ [eV]" % width
   plotter.add_edos(label, edos)

plotter.plot()
#plotter.animate()
