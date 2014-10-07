"""This module ..."""
from __future__ import print_function, division, unicode_literals

import abc
import os
import six
import collections

from time import ctime
from monty.os.path import which
from pymatgen.io.abinitio.events import EventsParser
from abipy.iotools.visualizer import Visualizer


__all__ = [
    "AbinitNcFile",
    "Has_Structure",
    "Has_ElectronBands",
    "Has_PhononBands",
]

@six.add_metaclass(abc.ABCMeta)
class AbinitFile(object):
    """
    Abstract base class defining the methods that must be  implemented 
    by the concrete classes representing the different files produced by ABINIT.
    """
    def __init__(self, filepath):
        self._filepath = os.path.abspath(filepath)

    def __repr__(self):
        return "<%s at %s, filepath = %s>" % (self.__class__.__name__, id(self), self.filepath)

    def __str__(self):
        return "<%s at %s, filepath = %s>" % (self.__class__.__name__, id(self), os.path.relpath(self.filepath))

    @classmethod
    def from_file(cls, filepath):
        """Initialize the object from a string."""
        if isinstance(filepath, cls):
            return filepath

        try:
            return cls(filepath)
        except:
            import traceback
            msg = traceback.format_exc()
            msg += "\n Perhaps the subclass %s must redefine the classmethod from_file\n" % cls
            raise ValueError(msg)

    @property
    def filepath(self):
        """Absolute path of the file."""
        return self._filepath

    @property
    def basename(self):
        """Basename of the file."""
        return os.path.basename(self.filepath)

    @property
    def filetype(self):
        """String defining the filetype."""
        return self.__class__.__name__

    def filestat(self):
        """Dictionary with file metadata"""
        return get_filestat(self.filepath)

    #@abc.abstractmethod
    #def close(self):


class AbinitTextFile(AbinitFile):
    """Class for the ABINIT main output file and the log file."""

    @property
    def events(self):
        """List of ABINIT events reported in the file."""
        try:
            return self._events
        except AttributeError:
            self._events = EventsParser().parse(self.filepath)
            return self._events

    @property
    def timer_data(self):
        """Timer data."""
        return self._timer_data
        # FIXME AbinitTimerParser no longer in pymatgen...
        #try:
        #    return self._timer_data

        #except AttributeError:
        #    parser = AbinitTimerParser()
        #    parser.parse(self.filepath)
        #    self._timer_data = parser
        #    return self._timer_data


class AbinitOutputFile(AbinitTextFile):
    """Class representing the main output file."""


class AbinitLogFile(AbinitTextFile):
    """Class representing the log file."""


@six.add_metaclass(abc.ABCMeta)
class AbinitNcFile(AbinitFile):
    """
    Abstract class representing a Netcdf file with data saved
    according to the ETSF-IO specifications (when available).
    """
    def ncdump(self, *nc_args, **nc_kwargs):
        """Returns a string with the output of ncdump."""
        return NcDumper(*nc_args, **nc_kwargs).dump(self.filepath)


@six.add_metaclass(abc.ABCMeta)
class Has_Structure(object):
    """Mixin class for `AbinitNcFile` containing crystallographic data."""

    @abc.abstractproperty
    def structure(self):
        """Returns the `Structure` object."""

    def show_bz(self):
        """
        Gives the plot (as a matplotlib object) of the symmetry line path in the Brillouin Zone.
        """
        return self.structure.hsym_kpath.get_kpath_plot()

    def export_structure(self, filepath):
        """
        Export the structure on file.

        returns:
            Instance of :class:`Visualizer`
        """
        return self.structure.export(filepath)

    def visualize_structure_with(self, visu_name):
        """
        Visualize the crystalline structure with the specified visualizer.

        See :class:`Visualizer` for the list of applications and formats supported.
        """
        visu = Visualizer.from_name(visu_name)

        for ext in visu.supported_extensions():
            ext = "." + ext
            try:
                return self.export_structure(ext)
            except visu.Error:
                pass
        else:
            raise visu.Error("Don't know how to export data for visu_name %s" % visu_name)


@six.add_metaclass(abc.ABCMeta)
class Has_ElectronBands(object):
    """Mixin class for `AbinitNcFile` containing electron data."""

    @abc.abstractproperty
    def ebands(self):
        """Returns the `ElectronBands` object."""

    #@property
    #def nsppol(self):
    #    return self.ebands.nsppol

    #@property
    #def nspinor(self):
    #    return self.ebands.nspinor

    #@property
    #def nspden(self):
    #    return self.ebands.nspden

    def plot_ebands(self, **kwargs):
        """
        Plot the electron energy bands. See the :func:`ElectronBands.plot` for the signature.""
        """
        return self.ebands.plot(**kwargs)

@six.add_metaclass(abc.ABCMeta)
class Has_PhononBands(object):
    """Mixin class for `AbinitNcFile` containing phonon data."""

    @abc.abstractproperty
    def phbands(self):
        """Returns the `PhononBands` object."""

    def plot_phbands(self, **kwargs):
        """
        Plot the electron energy bands. See the :func:`PhononBands.plot` for the signature.""
        """
        return self.phbands.plot(**kwargs)


class NcDumper(object):
    """Wrapper object for the ncdump tool."""

    def __init__(self, *nc_args, **nc_kwargs):
        """
        Args:
            nc_args:
                Arguments passed to ncdump.
            nc_kwargs:
                Keyword arguments passed to ncdump
        """
        self.nc_args = nc_args
        self.nc_kwargs = nc_kwargs

        self.ncdump = which("ncdump")

    def dump(self, filepath):
        """Returns a string with the output of ncdump."""
        if self.ncdump is None:
            return "Cannot find ncdump tool in PATH"
        else:
            from subprocess import check_output
            cmd = ["ncdump", filepath]
            return check_output(cmd)


_ABBREVS = [
    (1 << 50, 'Pb'),
    (1 << 40, 'Tb'),
    (1 << 30, 'Gb'),
    (1 << 20, 'Mb'),
    (1 << 10, 'kb'),
    (1, 'b'),
]


def size2str(size):
    """Convert size to string with units."""
    for factor, suffix in _ABBREVS:
        if size > factor:
            break
    return "%.2f " % (size / factor) + suffix


def get_filestat(filepath):
    stat = os.stat(filepath)
    return collections.OrderedDict([
        ("Name", os.path.basename(filepath)),
        ("Directory", os.path.dirname(filepath)),
        ("Size", size2str(stat.st_size)),
        ("Access Time", ctime(stat.st_atime)),
        ("Modification Time", ctime(stat.st_mtime)),
        ("Change Time", ctime(stat.st_ctime)),
    ])
