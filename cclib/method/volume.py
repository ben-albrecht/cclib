# -*- coding: utf-8 -*-
#
# This file is part of cclib (http://cclib.github.io), a library for parsing
# and interpreting the results of computational chemistry packages.
#
# Copyright (C) 2006-2014, the cclib development team
#
# The library is free software, distributed under the terms of
# the GNU Lesser General Public version 2.1 or later. You should have
# received a copy of the license along with cclib. You can also access
# the full license online at http://www.gnu.org/copyleft/lgpl.html.

"""Calculation methods related to volume based on cclib data."""

from __future__ import print_function
import copy

import numpy

try:
    from PyQuante.CGBF import CGBF
    from cclib.bridge import cclib2pyquante
    module_pyq = True
except:
    module_pyq = False

try:
    from pyvtk import *
    from pyvtk.DataSetAttr import *
    module_pyvtk = True
except:
    module_pyvtk = False

from cclib.parser.utils import convertor


class Volume(object):
    """Represent a volume in space.

    Required parameters:
       origin -- the bottom left hand corner of the volume
       topcorner -- the top right hand corner
       spacing -- the distance between the points in the cube

    Attributes:   
       data -- a numpy array of values for each point in the volume
               (set to zero at initialisation)
       numpts -- the numbers of points in the (x,y,z) directions

    """
    
    def __init__(self, origin, topcorner, spacing):
    
        self.origin = origin
        self.spacing = spacing
        self.topcorner = topcorner
        self.numpts = []
        for i in range(3):
            self.numpts.append(int((self.topcorner[i]-self.origin[i])/self.spacing[i]                                   + 1) )
        self.data = numpy.zeros( tuple(self.numpts), "d")

    def __str__(self):
        """Return a string representation."""
        return "Volume %s to %s (density: %s)" % (self.origin, self.topcorner,
                                                  self.spacing)

    def write(self, filename, format="Cube"):
        """Write the volume to file."""

        format = format.upper()

        if format.upper() not in ["VTK", "CUBE"]:
            raise "Format must be either VTK or Cube"
        elif format=="VTK":
            self.writeasvtk(filename)
        else:
            self.writeascube(filename)

    def writeasvtk(self, filename):
        if not module_pyvtk:
            raise Exception("You need to have pyvtk installed")
        ranges = (numpy.arange(self.data.shape[2]),
                  numpy.arange(self.data.shape[1]),
                  numpy.arange(self.data.shape[0]))
        v = VtkData(RectilinearGrid(*ranges), "Test",
                    PointData(Scalars(self.data.ravel(), "from cclib", "default")))
        v.tofile(filename)

    def integrate(self):
        boxvol = (self.spacing[0] * self.spacing[1] * self.spacing[2] *
                  convertor(1, "Angstrom", "bohr")**3)
        return sum(self.data.ravel()) * boxvol

    def integrate_square(self):
        boxvol = (self.spacing[0] * self.spacing[1] * self.spacing[2] *
                  convertor(1, "Angstrom", "bohr")**3)
        return sum(self.data.ravel()**2) * boxvol

    def writeascube(self, filename):
        # Remember that the units are bohr, not Angstroms
        convert = lambda x : convertor(x, "Angstrom", "bohr")
        ans = []
        ans.append("Cube file generated by cclib")
        ans.append("")
        format = "%4d%12.6f%12.6f%12.6f"
        origin = [convert(x) for x in self.origin]
        ans.append(format % (0, origin[0], origin[1], origin[2]))
        ans.append(format % (self.data.shape[0], convert(self.spacing[0]), 0.0, 0.0))
        ans.append(format % (self.data.shape[1], 0.0, convert(self.spacing[1]), 0.0))
        ans.append(format % (self.data.shape[2], 0.0, 0.0, convert(self.spacing[2])))
        line = []
        for i in range(self.data.shape[0]):
            for j in range(self.data.shape[1]):
                for k in range(self.data.shape[2]):
                    line.append(scinotation(self.data[i][j][k]))
                    if len(line)==6:
                        ans.append(" ".join(line))
                        line = []
                if line:
                    ans.append(" ".join(line))
                    line = []
        outputfile = open(filename, "w")
        outputfile.write("\n".join(ans))
        outputfile.close()

def scinotation(num):
   """Write in scientific notation

   >>> scinotation(1./654)
   ' 1.52905E-03'
   >>> scinotation(-1./654)
   '-1.52905E-03'
   """
   ans = "%10.5E" % num
   broken = ans.split("E")
   exponent = int(broken[1])
   if exponent<-99:
       return "  0.000E+00"
   if exponent<0:
       sign="-"
   else:
       sign="+"
   return ("%sE%s%s" % (broken[0],sign,broken[1][-2:])).rjust(12)                

def getbfs(coords, gbasis):
    """Convenience function for both wavefunction and density based on PyQuante Ints.py."""
    mymol = makepyquante(coords, [0 for x in coords])

    sym2powerlist = {
        'S' : [(0,0,0)],
        'P' : [(1,0,0),(0,1,0),(0,0,1)],
        'D' : [(2,0,0),(0,2,0),(0,0,2),(1,1,0),(0,1,1),(1,0,1)],
        'F' : [(3,0,0),(2,1,0),(2,0,1),(1,2,0),(1,1,1),(1,0,2),
               (0,3,0),(0,2,1),(0,1,2), (0,0,3)]
        }

    bfs = []
    for i,atom in enumerate(mymol):
        bs = gbasis[i]
        for sym,prims in bs:
            for power in sym2powerlist[sym]:
                bf = CGBF(atom.pos(),power)
                for expnt,coef in prims:
                    bf.add_primitive(expnt,coef)
                bf.normalize()
                bfs.append(bf)

    return bfs

def wavefunction(coords, mocoeffs, gbasis, volume):
    """Calculate the magnitude of the wavefunction at every point in a volume.
    
    Attributes:
        coords -- the coordinates of the atoms
        mocoeffs -- mocoeffs for one eigenvalue
        gbasis -- gbasis from a parser object
        volume -- a template Volume object (will not be altered)
    """
    bfs = getbfs(coords, gbasis)
    
    wavefn = copy.copy(volume)
    wavefn.data = numpy.zeros( wavefn.data.shape, "d")

    conversion = convertor(1,"bohr","Angstrom")
    x = numpy.arange(wavefn.origin[0], wavefn.topcorner[0]+wavefn.spacing[0], wavefn.spacing[0]) / conversion
    y = numpy.arange(wavefn.origin[1], wavefn.topcorner[1]+wavefn.spacing[1], wavefn.spacing[1]) / conversion
    z = numpy.arange(wavefn.origin[2], wavefn.topcorner[2]+wavefn.spacing[2], wavefn.spacing[2]) / conversion

    for bs in range(len(bfs)):
        data = numpy.zeros( wavefn.data.shape, "d")
        for i,xval in enumerate(x):
            for j,yval in enumerate(y):
                for k,zval in enumerate(z):
                    data[i, j, k] = bfs[bs].amp(xval,yval,zval)
        numpy.multiply(data, mocoeffs[bs], data)
        numpy.add(wavefn.data, data, wavefn.data)
    
    return wavefn

def electrondensity(coords, mocoeffslist, gbasis, volume):
    """Calculate the magnitude of the electron density at every point in a volume.
    
    Attributes:
        coords -- the coordinates of the atoms
        mocoeffs -- mocoeffs for all of the occupied eigenvalues
        gbasis -- gbasis from a parser object
        volume -- a template Volume object (will not be altered)

    Note: mocoeffs is a list of numpy arrays. The list will be of length 1
          for restricted calculations, and length 2 for unrestricted.
    """
    bfs = getbfs(coords, gbasis)
    
    density = copy.copy(volume)
    density.data = numpy.zeros( density.data.shape, "d")

    conversion = convertor(1,"bohr","Angstrom")
    x = numpy.arange(density.origin[0], density.topcorner[0]+density.spacing[0], density.spacing[0]) / conversion
    y = numpy.arange(density.origin[1], density.topcorner[1]+density.spacing[1], density.spacing[1]) / conversion
    z = numpy.arange(density.origin[2], density.topcorner[2]+density.spacing[2], density.spacing[2]) / conversion

    for mocoeffs in mocoeffslist:
        for mocoeff in mocoeffs:
            wavefn = numpy.zeros( density.data.shape, "d")
            for bs in range(len(bfs)):
                data = numpy.zeros( density.data.shape, "d")
                for i,xval in enumerate(x):
                    for j,yval in enumerate(y):
                        tmp = []
                        for k,zval in enumerate(z):
                            tmp.append(bfs[bs].amp(xval, yval, zval))
                        data[i,j,:] = tmp
                numpy.multiply(data, mocoeff[bs], data)
                numpy.add(wavefn, data, wavefn)
            density.data += wavefn**2
        
    if len(mocoeffslist) == 1:
        density.data = density.data*2. # doubly-occupied
    
    return density


if __name__=="__main__":

    try:
        import psyco
        psyco.full()
    except ImportError:
        pass

    from cclib.io import ccopen
    import logging
    a = ccopen("../../../data/Gaussian/basicGaussian03/dvb_sp_basis.log")
    a.logger.setLevel(logging.ERROR)
    c = a.parse()
    
    b = ccopen("../../../data/Gaussian/basicGaussian03/dvb_sp.out")
    b.logger.setLevel(logging.ERROR)
    d = b.parse()

    vol = Volume( (-3.0,-6,-2.0), (3.0, 6, 2.0), spacing=(0.25,0.25,0.25) )
    wavefn = wavefunction(d.atomcoords[0], d.mocoeffs[0][d.homos[0]],
                          c.gbasis, vol)
    assert abs(wavefn.integrate())<1E-6 # not necessarily true for all wavefns
    assert abs(wavefn.integrate_square() - 1.00)<1E-3 #   true for all wavefns
    print(wavefn.integrate(), wavefn.integrate_square())

    vol = Volume( (-3.0,-6,-2.0), (3.0, 6, 2.0), spacing=(0.25,0.25,0.25) )
    frontierorbs = [d.mocoeffs[0][(d.homos[0]-3):(d.homos[0]+1)]]
    density = electrondensity(d.atomcoords[0], frontierorbs, c.gbasis, vol)
    assert abs(density.integrate()-8.00)<1E-2
    print("Combined Density of 4 Frontier orbitals=",density.integrate())
