#!/usr/bin/env python
#
# This example shows how to plot a band structure
# using the eigenvalues stored in the GSR file produced by abinit.
from abipy.abilab import abiopen
import abipy.data as abidata

# Here we use one of the GSR files shipped with abipy.
# Replace filename with the path to your GSR file or your WFK file.
filename = abidata.ref_file("si_nscf_GSR.nc")

# Open the GSR file and extract the band structure. 
with abiopen(filename) as ncfile:
    ebands = ncfile.ebands

# Plot the band energies. Note that the labels for the k-points
# are found automatically by searching in an internal database.
ebands.plot(title="Silicon band structure")

# Alternatively you can use the optional argument klabels 
# that defines the mapping reduced_coordinates --> name of the k-point.
#klabels = {
#    (0.5, 0.0, 0.0) : "L",
#    (0.0, 0.0, 0.0) : "$\Gamma$",
#    (0.0, 0.5, 0.5) : "X",
#}

# and pass it to the plot method:
#ebands.plot(title="Silicon band structure", klabels=klabels)
