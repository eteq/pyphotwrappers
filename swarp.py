from __future__ import division, print_function

import os

from .astromatic import *
from . import utils

__all__ = ['Swarp']


class Swarp(AstromaticTool):
    defaultexecname = 'swarp'

    def __init__(self, execpath=None, autodecompress=True, keeptemps=False,
                 overwrite=True, verbose=False):
        super(Swarp, self).__init__(execpath, verbose=verbose)

        self.autodecompress = autodecompress
        self.keeptemps = keeptemps
        self.overwrite = overwrite

    def swarp_images(self, imgfns, headfns=None, weightfns=None):
        """
        Runs swarp on the given `imgfns`, possibly with the supplied header
        files and weight files.
        """
        if not self.overwrite and os.path.exists(self.cfg.IMAGEOUT_NAME):
            print("Swarp output file {0} exists, not running Swarp.".format(self.cfg.IMAGEOUT_NAME))
            return

        if isinstance(imgfns, basestring):
            imgfns = [imgfns]

        if headfns is not None and len(headfns) != len(imgfns):
            raise ValueError('Gave a different number of header files vs image files')
        if weightfns is not None:
            if len(weightfns) != len(imgfns):
                raise ValueError('Gave a different number of weight files vs image files')
            if self.cfg.WEIGHT_TYPE == 'NONE':
                raise ValueError("Weights were given, but WEIGHT_TYPE is 'NONE'")

        decompimgfns = [self._try_decompress(imfn) for imfn in imgfns]
        links = self._determine_links(imgfns, headfns, weightfns)

        oldwimg = self.cfg.WEIGHT_IMAGE
        try:
            self.cfg.WEIGHT_IMAGE = ''
            for target, linkname in links:
                if not os.path.exists(linkname):
                    os.symlink(target, linkname)

            infns = [imfn if dimfn is None else dimfn for imfn, dimfn in zip(imgfns, decompimgfns)]
            self._invoke_tool(infns, showoutput=True)
        finally:
            if not self.keeptemps:
                for decompfn in decompimgfns:
                    if decompfn is not None:
                        if os.path.isfile(decompfn):
                            os.remove(decompfn)
                for target, linkname in links:
                    if os.path.islink(linkname):
                        os.remove(linkname)
            self.cfg.WEIGHT_IMAGE = oldwimg

    def _determine_links(self, imgfns, headfns, weightfns):
        """
        Returns a sequence of (target, linkname) tuples of links to create for
        the header and weight files.
        """
        links = []
        for imgfn, headfn, wfn in zip(imgfns, headfns, weightfns):
            baseimgfn = imgfn.split('.fits')[0]
            links.append((headfn, baseimgfn + self.cfg.HEADER_SUFFIX))
            links.append((wfn, baseimgfn + self.cfg.WEIGHT_SUFFIX))
        return links

    def _try_decompress(self, fn):
        """
        runs funpack if necessary.

        Returns a file name for the decompressed file, or None if decompression
        not needed
        """
        import time
        import subprocess

        if not self.autodecompress:
            return None  # bail immediately

        for ext in utils.fitsextension_to_decompresser:
            if fn.endswith(ext):
                decompresser = utils.which_path(utils.fitsextension_to_decompresser[ext])
                break
        else:
            return None  # not a decompressible file

        decompfn = os.path.split(fn[:-len(ext)])[1]  # the base file name
        if self.autodecompress is True:
            decompfn = os.path.join(os.path.split(fn)[0], decompfn)
        elif self.autodecompress == 'tempfile':
            decompfn = os.path.join(tempfile.gettempdir(), tempfile.gettempprefix() + decompfn)
        else:
            # use it as the path to where the decompressed file should go
            decompfn = os.path.join(self.autodecompress, decompfn)

        if os.path.exists(decompfn):
            #assume it has already been decompressed
            if self.verbose:
                print("Not decompressing {0} because it already exists as {1}".format(fn, decompfn))
        else:
            if self.verbose:
                print('Running {prog} to extract file {0} to {1}'.format(fn, decompfn, prog=decompresser))
            sttime = time.time()
            retcode = subprocess.call([decompresser, '-O', decompfn, fn])
            etime = time.time()
            if retcode != 0:
                raise OSError('{prog} failed with return code '.format(prog=decompresser) + str(retcode))
            if self.verbose:
                print('{prog} finished in {0} secs'.format(etime - sttime, prog=decompresser))

        return decompfn
