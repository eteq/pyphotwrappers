from __future__ import division, print_function

import os
import tempfile

from .astromatic import *

__all__ = ['Sextractor']


class Sextractor(AstromaticTool):
    """
    Driver class for scripting Sextractor

    Parameters
    ----------
    execpath : None or str
        Path to executable or None to search for it
    autodecompress : bool
        If True, will automatically use ``funpack`` to unpack input files that
        end in ``.fz`` (SExtractor can't handle fits compression).  Can be a
        string, in which case it points to the executable for funpack.
    renameoutputs : str or None
        If present, indicates that the output files should be renamed to the
        provided string pattern.  The string can include '{path}', '{fn}',
        '{input}', and '{object}', meaning the path and name from the
        configuration, the base name of the input file, and the 'OBJECT' fits
        header keyword (if present).
    """
    defaultexecname = 'sex'

    def __init__(self, execpath=None, autodecompress=True, renameoutputs=None,
                 checkimgpath=None, verbose=False):
        super(Sextractor, self).__init__(execpath, verbose=verbose)

        self._parse_outputs(self._invoke_tool(['-dp'])[0])
        self.reset_outputs()
        self.choose_conv_filter('default')

        self.cfg.PARAMETERS_NAME = ProxyInputFile('PLACEHOLDER: WILL BE POPULATED BY Sextractor CLASS')

        self.autodecompress = autodecompress
        self.renameoutputs = renameoutputs
        self.checkimgpath = checkimgpath

    def _parse_outputs(self, contents):
        self.valid_outputs = values = []
        self.output_comments = comments = {}
        for l in contents.split('\n'):
            l = l.strip()
            if l != '':
                values.append(l[:24].replace('#', '').strip())
                comments[values[-1]] = l[24:]

    def _invoke_tool(self, *args, **kwargs):
        if self.cfg is not None and hasattr(self.cfg.PARAMETERS_NAME, 'content'):
            oldcontent = self.cfg.PARAMETERS_NAME.content
        else:
            oldcontent = None
        try:
            if oldcontent is not None and self.cfg.PARAMETERS_NAME.content.startswith('PLACEHOLDER'):
                self.cfg.PARAMETERS_NAME.content = '\n'.join(self.outputs)
            return super(Sextractor, self)._invoke_tool(*args, **kwargs)
        finally:
            if oldcontent is not None:
                self.cfg.PARAMETERS_NAME.content = oldcontent

    def choose_conv_filter(self, fname):
        if fname not in _CONV_FILTER_NAMES:
            raise ValueError('Invalid convolution filter name ' + fname)

        infilter = False
        flines = []
        for l in _CONV_FILTER_FILE_CONTENTS.split('\n'):
            if l.startswith('##'):
                infilter = l[2:-5] == fname
            elif infilter:
                flines.append(l)
        fstr = '\n'.join(flines)
        self.set_conv_filter(fstr)
        return fstr

    def set_conv_filter(self, fcontents):
        self.cfg.FILTER_NAME = ProxyInputFile(fcontents)

    def list_conv_filters(self):
        res = []
        for nm in _CONV_FILTER_NAMES:
            res.append((nm, _CONV_FILTER_DESC[nm]))
        return res

    def reset_outputs(self):
        """
        Resets the output columns to Sextractor's defaults
        """
        self.outputs = ['NUMBER',
                        'FLUXERR_ISO',
                        'FLUX_AUTO',
                        'FLUXERR_AUTO',
                        'X_IMAGE',
                        'Y_IMAGE',
                        'FLAGS']

    def set_outputs_from_scamp(self, scamp=None, reset=True):
        """
        Sets the outputs based on the outputs SCAMP wants, either for the
        defaults or a provided instance.

        Parameters
        ----------
        scamp : None or a Scamp object
            If None, assumes the outputs SCAMP defaults to wanting.  Otherwise,
            infers the columns from the Scamp object
        """
        if scamp is None:
            outputs = ('XWIN_IMAGE', 'YWIN_IMAGE', 'FLUX_AUTO',
                       'FLUXERR_AUTO', 'FLUX_RADIUS', 'ERRAWIN_IMAGE',
                       'ERRBWIN_IMAGE', 'ERRTHETAWIN_IMAGE', 'FLAGS')
        else:
            outputs = ['FLAGS', 'FLUX_RADIUS']
            outputs.extend(scamp.cfg.CENTROID_KEYS.split(','))
            outputs.extend(scamp.cfg.CENTROIDERR_KEYS.split(','))
            outputs.extend(scamp.cfg.DISTORT_KEYS.split(','))
            outputs.extend(scamp.cfg.PHOTFLUX_KEY.split(','))
            outputs.extend(scamp.cfg.PHOTFLUXERR_KEY.split(','))
            outputs = set(outputs)  # remove duplicates

        if reset:
            self.outputs = []
        self.add_outputs(outputs)

        self.cfg.CATALOG_TYPE = 'FITS_LDAC'

    def add_outputs(self, vals):
        """
        Adds the provided value(s) to the output list, checking if they are
        valid or already present
        """
        if isinstance(vals, basestring):
            vals = [vals]
        for v in vals:
            if v not in self.valid_outputs:
                raise ValueError(str(v) + ' is not a valid output')
            if v not in self.outputs:
                self.outputs.append(v)

    def use_proxy_catalog(self, outtype=None):
        """
        Switches to using a proxy for the output catalog so that the results are
        stored in this object rather than saved out to a file.

        Parameters
        ----------
        outtype : str or None
            The CATALOG_TYPE
        """
        if outtype is not None:
            validtypes = [t.strip() for t in self.cfg.comments['CATALOG_TYPE']
                          .replace('or', ',').split(',') if t.strip() != '']
            if outtype not in validtypes:
                raise ValueError('Requested output type {0} is not one of the '
                                 'valid types:{1}'.format(outtype, validtypes))
            self.cfg.CATALOG_TYPE = outtype
        self.cfg.CATALOG_NAME = ProxyOutputFile()

    def get_output(self, astable=True):
        from astropy.io import ascii
        if hasattr(self.cfg.CATALOG_NAME, 'content'):
            if self.verbose:
                print("Getting output from stored content")
            content = self.cfg.CATALOG_NAME.content
        else:
            if self.verbose:
                print("Can't get output if a proxy output was not used - "
                      "reading from file " + self.cfg.CATALOG_NAME)
            if self.renameoutputs:
                catfn = self.get_renamed_output_fns()[0].values()[0]
            else:
                catfn = self.cfg.CATALOG_NAME
            with open(catfn, 'rb') as f:
                content = f.read()

        if astable:
            lcattype = self.cfg.CATALOG_TYPE.lower()
            if 'votable' in lcattype:
                from astropy.io import votable
                from io import BytesIO
                return votable.parse(BytesIO(content))
            elif 'ascii' in lcattype:
                return ascii.read(content, Reader=ascii.SExtractor)
            elif 'fits' in lcattype:
                from astropy.io import fits
                return fits.HDUList.fromstring(content)[2].data
        else:
            return content

    def sextract_single(self, imgfn=None):
        """
        Run sextractor in single output mode

        Parameters
        ----------
        imgfn : str or None
            The input file or None to use `lastimgfn`
        """
        if imgfn is None:
            imgfn = getattr(self, 'lastimgfn', None)

        decompfn = self._try_decompress(imgfn)
        try:
            self._invoke_tool([imgfn if decompfn is None else decompfn], showoutput=True)
            self.lastimgfn = imgfn

            if self.renameoutputs:
                self._rename_outputs()  # uses lastimgfn to figure out the new names
        finally:
            if decompfn is not None:
                if os.path.isfile(decompfn):
                    os.remove(decompfn)

    def sextract_double(self, masterimgfn=None, analysisimgfn=None):
        """
        Run sextractor in single output mode

        Parameters
        ----------
        masterimgfn : str or None
            The input file or None to use `lastmasterimgfn`
        analysisimgfn : str or None
            The input analysis file or None to use `lastimgfn`
        """
        if masterimgfn is None:
            masterimgfn = getattr(self, 'lastmasterimgfn', None)
        if analysisimgfn is None:
            analysisimgfn = getattr(self, 'lastimgfn', None)

        masterdecompfn = self._try_decompress(masterimgfn)
        analysisdecompfn = self._try_decompress(analysisimgfn)
        try:
            self._invoke_tool([masterimgfn if masterdecompfn is None else masterdecompfn,
                               analysisimgfn if analysisdecompfn is None else analysisdecompfn],
                              showoutput=True)

            self.lastimgfn = analysisimgfn
            self.lastmasterimgfn = masterimgfn

            if self.renameoutputs:
                self._rename_outputs()  # uses lastimgfn to figure out the new names
        finally:
            if analysisdecompfn is not None:
                if os.path.isfile(analysisdecompfn):
                    os.remove(analysisdecompfn)
            if masterdecompfn is not None:
                if os.path.isfile(masterdecompfn):
                    os.remove(masterdecompfn)

    def get_renamed_output_fns(self):
        """
        Gets the names that the sextractor outputs will get mapped to if
        `renameoutputs` is True.

        Returns
        -------
        catmap : dict
            Mapping of catalog file names as written by sextractor mapped to new
            names.
        xmlmap : dict
            Mapping of XML file names as written by sextractor mapped to new
            names.
        cimgmap : dict
            Mapping of check image file names as written by sextractor to new
            names.
        """

        inputfn = self.lastimgfn
        input_ = os.path.split(inputfn)[1].split('.fits')[0]

        if '{object}' in self.renameoutputs:
            from astropy.io import fits
            with fits.open(inputfn) as f:
                for hdu in f:
                    if 'OBJECT' in hdu.header:
                        object_ = hdu.header['OBJECT']
                        break
                else:
                    object_ = ''
        else:
            object_ = None

        #main catalog
        oldcatfn = self.cfg.CATALOG_NAME
        path, fn = os.path.split(oldcatfn)
        newcatfn = self.renameoutputs.format(
                path=path + ('' if path.endswith(os.path.sep) or path == '' else os.path.sep),
                fn=fn, object=object_, input=input_)
        catmap = {oldcatfn: newcatfn}

        #XML output
        oldxmlfn = self.cfg.XML_NAME
        path, fn = os.path.split(oldxmlfn)
        newxmlfn = self.renameoutputs.format(
                path=path + ('' if path.endswith(os.path.sep) or path == '' else os.path.sep),
                fn=fn, object=object_, input=input_)
        xmlmap = {oldxmlfn: newxmlfn}

        cimgmap = {}
        for cimgfn in self.cfg.CHECKIMAGE_NAME.split(','):
            cimgfn = cimgfn.strip() + '.fits'  # just in case
            path, fn = os.path.split(cimgfn)
            if self.checkimgpath:
                path = self.checkimgpath

            cimgmap[cimgfn] = self.renameoutputs.format(
                path=path + ('' if path.endswith(os.path.sep) or path == '' else os.path.sep),
                fn=fn, object=object_, input=input_)

        return catmap, xmlmap, cimgmap

    def _rename_outputs(self):
        from shutil import move

        catmap, xmlmap, cimgmap = self.get_renamed_output_fns()

        #rename main catalog
        for ofn, nfn in catmap.iteritems():
            if os.path.isfile(ofn):
                if self.verbose:
                    print("Moving catalog output {0} to {1}".format(ofn, nfn))
                move(ofn, nfn)

        #rename XML output if present
        for ofn, nfn in xmlmap.iteritems():
            if os.path.isfile(ofn):
                if self.verbose:
                    print("Moving XML output {0} to {1}".format(ofn, nfn))
                move(ofn, nfn)

        #rename checkimages if present
        for ofn, nfn in cimgmap.iteritems():
            if os.path.isfile(ofn):
                if self.verbose:
                    print("Moving Check image {0} to {1}".format(ofn, nfn))
                move(ofn, nfn)

    # used by _try_decompress
    exttodecompresser = {'.fz': 'funpack', '.gz': 'gunzip'}

    def _try_decompress(self, fn):
        """
        runs funpack if necessary.

        Returns a (closed) temporary file object, which needs to be manually
        deleted when no longer needed, or None if funpack is unnecessary
        """
        import time
        import subprocess

        from .utils import which_path

        if not self.autodecompress:
            return None  # bail immediately

        for ext in self.exttodecompresser:
            if fn.endswith(ext):
                decompresser = which_path(self.exttodecompresser[ext])
                break
        else:
            return None  # not a decompressable file

        tfn = os.path.split(fn[:-len(ext)])[1]
        tfn = os.path.join(tempfile.gettempdir(), tempfile.gettempprefix() + tfn)

        if os.path.exists(tfn):
            os.remove(tfn)

        if self.verbose:
            print('Running {prog} to extract file {0} to {1}'.format(fn, tfn, prog=decompresser))
        sttime = time.time()
        retcode = subprocess.call([decompresser, '-O', tfn, fn])
        etime = time.time()
        if retcode != 0:
            raise OSError('{prog} failed with return code '.format(prog=decompresser) + str(retcode))
        if self.verbose:
            print('{prog} finished in {0} secs'.format(etime - sttime, prog=decompresser))

        return tfn

    def ds9_mark(self, mask=None, sizekey='FLUX_RADIUS', ds9=None, doload=True, clearmarks=True, frame=None):
        """
        Mark the sextracted outputs on ds9.

        Parameters
        ----------
        mask : array or None
            A mask that will be applied to the x/y/size arrays to get the sample
            to mark or None to show everything
        sizekey : str or number
            The name of the column to use as the size of the circles or a
            number for them all to be the same.  If key is missing, default=5.
        ds9 : None or pysao.ds9 instance
            if None, a new DS9 will be started, otherwise the instance to use
        doload : bool
            If True, loads the file.
        clearmarks : bool
            If True, clears the marks

        """
        import pysao

        #try to get in existing ds9 if one wasn't given, otherwise make one
        if ds9 is None:
            ds9 = getattr(self, 'lastds9', None)

            if ds9 is not None:
                #check that it's still alive
                try:
                    ds9.get('')  # should just give all the XPA options
                except RuntimeError:
                    # exernally killed
                    self.lastds9 = ds9 = None

            if ds9 is None:
                if self.verbose:
                    print("didn't find old ds9 - starting a new one")
                ds9 = self.lastds9 = pysao.ds9()

        currfn = ds9.get('iis filename').strip()
        if currfn != self.lastimgfn:
            if self.verbose:
                print("Current filename {0} does not match {1}.  Reloading.".format(currfn, self.lastimgfn))
            ds9.load_fits(self.lastimgfn)
        elif clearmarks:
            #delete existing marks
            ds9.set('regions delete all')

        tab = self.get_output()
        if isinstance(sizekey, basestring):
            try:
                sz = tab[sizekey]
            except KeyError:
                if self.verbose:
                    print("didn't find key {0} defaulting to 5 px".format(sizekey))
                sz = [5] * len(tab)
        else:
            sz = [sizekey] * len(tab)

        try:
            x = tab['X_IMAGE']
            y = tab['Y_IMAGE']
        except KeyError:
            try:
                x = tab['XWIN_IMAGE']
                y = tab['YWIN_IMAGE']
            except KeyError:
                raise KeyError('Could not find X_IMAGE/Y_IMAGE or XWIN_IMAGE/YWIN_IMAGE')

        if mask is not None:
            x = x[mask]
            y = y[mask]
            sz = np.array(sz)[mask]

        ds9.mark(x, y, sz)

        return ds9

    def load_cfg_from_xml(self, xmlfile, onlyimg=False, compressedimgpaths=['.'],
                          tempfileprefix=os.path.join(tempfile.gettempdir(), tempfile.gettempprefix())):
        """
        Loads a previous configuration from the specified sextractor XML file.

        This includes setting `lastimgfn` to match the generate file.

        Parameters
        ----------
        xmlfile : str
            The path to the xml file to load from.
        onlyimg : bool
            Loads only the image and nothing else.
        compressedimgpaths : list of str
            Possible paths to search for *compressed* image files (e.g.,
            ``.fits.fz`` files).
        tempfileprefix : str
            the prefix for temporary files on the system used to generate this
            xml file.  The default should be right if you do this in the same
            place you did the reductions.

        .. note::
            `compressedimgpaths` is only necessary because we have to decompress
            a compressed fits file if it's the input, which is done in a
            temporary file.  So this path is necessary to map that onto a location.


        """
        from xml.etree import cElementTree as et

        tree = et.parse(xmlfile)

        #make compressedimgpaths into a directory list
        compressedpathset = []
        for p in compressedimgpaths:
            if os.path.isfile(p):
                compressedpathset.append(os.path.split(p)[0])
            else:
                compressedpathset.append(p)
        compressedpathset = set(compressedpathset)

        #first find the input file and see if it can be found
        inputfn = tree.find(".//PARAM[@name='Image_Name']").get('value')
        if not os.path.isfile(inputfn):
            #search for compressed versions in the compressedpathset
            newinputfn = None
            truebaseinputfn = inputfn.replace(tempfileprefix, '')
            for path in compressedpathset:
                basefn = os.path.join(path, truebaseinputfn)
                for ext in self.exttodecompresser:
                    if os.path.isfile(basefn + ext):
                        newinputfn = basefn + ext
                        break
                if newinputfn is not None:
                    inputfn = newinputfn
                    break
            else:
                print('Could not find input file {0}, nor a compressed '
                      'version of it in {1}. Will set `lastimgfn` attribute '
                      'to None'.format(truebaseinputfn, compressedpathset))
                inputfn = None

        #now find all the configuration
        cfgparams = tree.findall(".//RESOURCE[@ID='Config']/PARAM")
        #filter out those that are not actually configuration settings
        cfgparams = [p for p in cfgparams if not p.get('name') in ('Command_Line', 'Prefs_Name')]

        #now find the outputs
        outputparams = tree.findall(".//TABLE[@ID='Source_List']/FIELD")

        #backup settings so we can revert if need be
        oldcfgset = self.cfg._config_settings.copy()
        oldoutputs = self.outputs[:]
        try:
            if not onlyimg:
                for p in cfgparams:
                    cfgnm = p.get('name').upper()
                    val = p.get('value')

                    if 'meta.file' in p.get('ucd'):
                        # need to check for things that look like temp files, and
                        # skip them if they are supposed to be proxies
                        if val.startswith(tempfileprefix):
                            #mean's it should be some sort of proxy
                            if 'Proxy' in self.cfg[cfgnm].__class__.__name__:
                                if self.verbose:
                                    print('Config setting {0} is being left as a '
                                          'proxy'.format(cfgnm))
                                continue  # means its just fine as a proxy
                            else:
                                print('Config setting {0} looks like a temporary '
                                      'file but is not a proxy.  Setting it to a '
                                      'temporary file, but this is probably '
                                      'invalid.'.format(cfgnm))

                    if p.get('datatype') == 'boolean':
                        #need to map 'T'/'F' to 'Y'/'N' for booleans
                        if val == 'T':
                            self.cfg[cfgnm] = 'Y'
                        elif val == 'F':
                            self.cfg[cfgnm] = 'N'
                        else:
                            raise ValueError('Invalid XML boolean value ' + str(val))
                    else:
                        self.cfg[cfgnm] = val

                del self.outputs[:len(self.outputs)]  # clear old outputs
                self.add_outputs([p.get('name') for p in outputparams])

            self.lastimgfn = inputfn  # this might end up None, but that's fine because the previous value would be invalid anyway
        except Exception:
            #put back in the old settings
            self.cfg._config_settings.clear()
            self.cfg._config_settings.update(oldcfgset)
            del self.outputs[:len(self.outputs)]
            self.outputs[:] = oldoutputs
            #don't need to revert lastimgfn because it's the last thing in the try
            raise


def _generate_conv_filter_files_string(fns=None):
    from glob import glob

    lns = []
    if fns is None:
        fns = glob('*.conv')
    for fn in fns:
        lns.append('##' + fn)
        with open(fn) as f:
            for l in f:
                lns.append(l[:-1])
    return '\n'.join(lns)

#convolution filters for Sextractor
_CONV_FILTER_FILE_CONTENTS = """
##default.conv
CONV NORM
# 3x3 ``all-ground'' convolution mask with FWHM = 2 pixels.
1 2 1
2 4 2
1 2 1
##block_3x3.conv
CONV NORM
# 3x3 convolution mask of a block-function PSF (ex: DeNIS PSF).
1 1 1
1 1 1
1 1 1
##gauss_1.5_3x3.conv
CONV NORM
# 3x3 convolution mask of a gaussian PSF with FWHM = 1.5 pixels.
0.109853 0.300700 0.109853
0.300700 0.823102 0.300700
0.109853 0.300700 0.109853
##gauss_2.0_3x3.conv
CONV NORM
# 3x3 convolution mask of a gaussian PSF with FWHM = 2.0 pixels.
0.260856 0.483068 0.260856
0.483068 0.894573 0.483068
0.260856 0.483068 0.260856

##gauss_2.0_5x5.conv
CONV NORM
# 5x5 convolution mask of a gaussian PSF with FWHM = 2.0 pixels.
0.006319 0.040599 0.075183 0.040599 0.006319
0.040599 0.260856 0.483068 0.260856 0.040599
0.075183 0.483068 0.894573 0.483068 0.075183
0.040599 0.260856 0.483068 0.260856 0.040599
0.006319 0.040599 0.075183 0.040599 0.006319
##gauss_2.5_5x5.conv
CONV NORM
# 5x5 convolution mask of a gaussian PSF with FWHM = 2.5 pixels.
0.034673 0.119131 0.179633 0.119131 0.034673
0.119131 0.409323 0.617200 0.409323 0.119131
0.179633 0.617200 0.930649 0.617200 0.179633
0.119131 0.409323 0.617200 0.409323 0.119131
0.034673 0.119131 0.179633 0.119131 0.034673
##gauss_3.0_5x5.conv
CONV NORM
# 5x5 convolution mask of a gaussian PSF with FWHM = 3.0 pixels.
0.092163 0.221178 0.296069 0.221178 0.092163
0.221178 0.530797 0.710525 0.530797 0.221178
0.296069 0.710525 0.951108 0.710525 0.296069
0.221178 0.530797 0.710525 0.530797 0.221178
0.092163 0.221178 0.296069 0.221178 0.092163
##gauss_3.0_7x7.conv
CONV NORM
# 7x7 convolution mask of a gaussian PSF with FWHM = 3.0 pixels.
0.004963 0.021388 0.051328 0.068707 0.051328 0.021388 0.004963
0.021388 0.092163 0.221178 0.296069 0.221178 0.092163 0.021388
0.051328 0.221178 0.530797 0.710525 0.530797 0.221178 0.051328
0.068707 0.296069 0.710525 0.951108 0.710525 0.296069 0.068707
0.051328 0.221178 0.530797 0.710525 0.530797 0.221178 0.051328
0.021388 0.092163 0.221178 0.296069 0.221178 0.092163 0.021388
0.004963 0.021388 0.051328 0.068707 0.051328 0.021388 0.004963
##gauss_4.0_7x7.conv
CONV NORM
# 7x7 convolution mask of a gaussian PSF with FWHM = 4.0 pixels.
0.047454 0.109799 0.181612 0.214776 0.181612 0.109799 0.047454
0.109799 0.254053 0.420215 0.496950 0.420215 0.254053 0.109799
0.181612 0.420215 0.695055 0.821978 0.695055 0.420215 0.181612
0.214776 0.496950 0.821978 0.972079 0.821978 0.496950 0.214776
0.181612 0.420215 0.695055 0.821978 0.695055 0.420215 0.181612
0.109799 0.254053 0.420215 0.496950 0.420215 0.254053 0.109799
0.047454 0.109799 0.181612 0.214776 0.181612 0.109799 0.047454
##gauss_5.0_9x9.conv
CONV NORM
# 9x9 convolution mask of a gaussian PSF with FWHM = 5.0 pixels.
0.030531 0.065238 0.112208 0.155356 0.173152 0.155356 0.112208 0.065238 0.030531
0.065238 0.139399 0.239763 0.331961 0.369987 0.331961 0.239763 0.139399 0.065238
0.112208 0.239763 0.412386 0.570963 0.636368 0.570963 0.412386 0.239763 0.112208
0.155356 0.331961 0.570963 0.790520 0.881075 0.790520 0.570963 0.331961 0.155356
0.173152 0.369987 0.636368 0.881075 0.982004 0.881075 0.636368 0.369987 0.173152
0.155356 0.331961 0.570963 0.790520 0.881075 0.790520 0.570963 0.331961 0.155356
0.112208 0.239763 0.412386 0.570963 0.636368 0.570963 0.412386 0.239763 0.112208
0.065238 0.139399 0.239763 0.331961 0.369987 0.331961 0.239763 0.139399 0.065238
0.030531 0.065238 0.112208 0.155356 0.173152 0.155356 0.112208 0.065238 0.030531
##mexhat_1.5_5x5.conv
CONV NORM
# 5x5 convolution mask of a mexican-hat for images with FWHM~1.5 pixels.
-0.000109 -0.002374 -0.006302 -0.002374 -0.000109
-0.002374 -0.032222 -0.025569 -0.032222 -0.002374
-0.006302 -0.025569 0.276021 -0.025569 -0.006302
-0.002374 -0.032222 -0.025569 -0.032222 -0.002374
-0.000109 -0.002374 -0.006302 -0.002374 -0.000109
##mexhat_2.0_7x7.conv
CONV NORM
# 7x7 convolution mask of a mexican-hat for images with FWHM~2.0 pixels.
-0.000006 -0.000132 -0.000849 -0.001569 -0.000849 -0.000132 -0.000006
-0.000132 -0.002989 -0.017229 -0.028788 -0.017229 -0.002989 -0.000132
-0.000849 -0.017229 -0.042689 0.023455 -0.042689 -0.017229 -0.000849
-0.001569 -0.028788 0.023455 0.356183 0.023455 -0.028788 -0.001569
-0.000849 -0.017229 -0.042689 0.023455 -0.042689 -0.017229 -0.000849
-0.000132 -0.002989 -0.017229 -0.028788 -0.017229 -0.002989 -0.000132
-0.000006 -0.000132 -0.000849 -0.001569 -0.000849 -0.000132 -0.000006
##mexhat_2.5_7x7.conv
CONV NORM
# 7x7 convolution mask of a mexican-hat for images with FWHM~2.5 pixels.
-0.000284 -0.002194 -0.007273 -0.010722 -0.007273 -0.002194 -0.000284
-0.002194 -0.015640 -0.041259 -0.050277 -0.041259 -0.015640 -0.002194
-0.007273 -0.041259 -0.016356 0.095837 -0.016356 -0.041259 -0.007273
-0.010722 -0.050277 0.095837 0.402756 0.095837 -0.050277 -0.010722
-0.007273 -0.041259 -0.016356 0.095837 -0.016356 -0.041259 -0.007273
-0.002194 -0.015640 -0.041259 -0.050277 -0.041259 -0.015640 -0.002194
-0.000284 -0.002194 -0.007273 -0.010722 -0.007273 -0.002194 -0.000284
##mexhat_3.0_9x9.conv
CONV NORM
# 9x9 convolution mask of a mexican-hat for images with FWHM~3.0 pixels.
-0.000041 -0.000316 -0.001357 -0.003226 -0.004294 -0.003226 -0.001357 -0.000316 -0.000041
-0.000316 -0.002428 -0.010013 -0.022204 -0.028374 -0.022204 -0.010013 -0.002428 -0.000316
-0.001357 -0.010013 -0.035450 -0.054426 -0.050313 -0.054426 -0.035450 -0.010013 -0.001357
-0.003226 -0.022204 -0.054426 0.033057 0.164532 0.033057 -0.054426 -0.022204 -0.003226
-0.004294 -0.028374 -0.050313 0.164532 0.429860 0.164532 -0.050313 -0.028374 -0.004294
-0.003226 -0.022204 -0.054426 0.033057 0.164532 0.033057 -0.054426 -0.022204 -0.003226
-0.001357 -0.010013 -0.035450 -0.054426 -0.050313 -0.054426 -0.035450 -0.010013 -0.001357
-0.000316 -0.002428 -0.010013 -0.022204 -0.028374 -0.022204 -0.010013 -0.002428 -0.000316
-0.000041 -0.000316 -0.001357 -0.003226 -0.004294 -0.003226 -0.001357 -0.000316 -0.000041
##mexhat_4.0_9x9.conv
CONV NORM
# 9x9 convolution mask of a mexican-hat for images with FWHM~4.0 pixels.
-0.002250 -0.007092 -0.015640 -0.024467 -0.028187 -0.024467 -0.015640 -0.007092 -0.002250
-0.007092 -0.021141 -0.041403 -0.054742 -0.057388 -0.054742 -0.041403 -0.021141 -0.007092
-0.015640 -0.041403 -0.057494 -0.024939 0.008058 -0.024939 -0.057494 -0.041403 -0.015640
-0.024467 -0.054742 -0.024939 0.145167 0.271470 0.145167 -0.024939 -0.054742 -0.024467
-0.028187 -0.057388 0.008058 0.271470 0.459236 0.271470 0.008058 -0.057388 -0.028187
-0.024467 -0.054742 -0.024939 0.145167 0.271470 0.145167 -0.024939 -0.054742 -0.024467
-0.015640 -0.041403 -0.057494 -0.024939 0.008058 -0.024939 -0.057494 -0.041403 -0.015640
-0.007092 -0.021141 -0.041403 -0.054742 -0.057388 -0.054742 -0.041403 -0.021141 -0.007092
-0.002250 -0.007092 -0.015640 -0.024467 -0.028187 -0.024467 -0.015640 -0.007092 -0.002250
##mexhat_5.0_11x11.conv
CONV NORM
# 11x11 convolution mask of a mexican-hat for images with FWHM~5.0 pixels.
-0.002172 -0.005657 -0.011702 -0.019279 -0.025644 -0.028106 -0.025644 -0.019279 -0.011702 -0.005657 -0.002172
-0.005657 -0.014328 -0.028098 -0.042680 -0.052065 -0.054833 -0.052065 -0.042680 -0.028098 -0.014328 -0.005657
-0.011702 -0.028098 -0.049016 -0.059439 -0.051288 -0.043047 -0.051288 -0.059439 -0.049016 -0.028098 -0.011702
-0.019279 -0.042680 -0.059439 -0.030431 0.047481 0.093729 0.047481 -0.030431 -0.059439 -0.042680 -0.019279
-0.025644 -0.052065 -0.051288 0.047481 0.235153 0.339248 0.235153 0.047481 -0.051288 -0.052065 -0.025644
-0.028106 -0.054833 -0.043047 0.093729 0.339248 0.473518 0.339248 0.093729 -0.043047 -0.054833 -0.028106
-0.025644 -0.052065 -0.051288 0.047481 0.235153 0.339248 0.235153 0.047481 -0.051288 -0.052065 -0.025644
-0.019279 -0.042680 -0.059439 -0.030431 0.047481 0.093729 0.047481 -0.030431 -0.059439 -0.042680 -0.019279
-0.011702 -0.028098 -0.049016 -0.059439 -0.051288 -0.043047 -0.051288 -0.059439 -0.049016 -0.028098 -0.011702
-0.005657 -0.014328 -0.028098 -0.042680 -0.052065 -0.054833 -0.052065 -0.042680 -0.028098 -0.014328 -0.005657
-0.002172 -0.005657 -0.011702 -0.019279 -0.025644 -0.028106 -0.025644 -0.019279 -0.011702 -0.005657 -0.002172
##tophat_1.5_3x3.conv
CONV NORM
# 3x3 convolution mask of a top-hat PSF with diameter = 1.5 pixels.
0.000000 0.180000 0.000000
0.180000 1.000000 0.180000
0.000000 0.180000 0.000000
##tophat_2.0_3x3.conv
CONV NORM
# 3x3 convolution mask of a top-hat PSF with diameter = 2.0 pixels.
0.080000 0.460000 0.080000
0.460000 1.000000 0.460000
0.080000 0.460000 0.080000
##tophat_2.5_3x3.conv
CONV NORM
# 3x3 convolution mask of a top-hat PSF with diameter = 2.5 pixels.
0.260000 0.700000 0.260000
0.700000 1.000000 0.700000
0.260000 0.700000 0.260000
##tophat_3.0_3x3.conv
CONV NORM
# 3x3 convolution mask of a top-hat PSF with diameter = 3.0 pixels.
0.560000 0.980000 0.560000
0.980000 1.000000 0.980000
0.560000 0.980000 0.560000
##tophat_4.0_5x5.conv
CONV NORM
# 5x5 convolution mask of a top-hat PSF with diameter = 4.0 pixels.
0.000000 0.220000 0.480000 0.220000 0.000000
0.220000 0.990000 1.000000 0.990000 0.220000
0.480000 1.000000 1.000000 1.000000 0.480000
0.220000 0.990000 1.000000 0.990000 0.220000
0.000000 0.220000 0.480000 0.220000 0.000000
##tophat_5.0_5x5.conv
CONV NORM
# 5x5 convolution mask of a top-hat PSF with diameter = 5.0 pixels.
0.150000 0.770000 1.000000 0.770000 0.150000
0.770000 1.000000 1.000000 1.000000 0.770000
1.000000 1.000000 1.000000 1.000000 1.000000
0.770000 1.000000 1.000000 1.000000 0.770000
0.150000 0.770000 1.000000 0.770000 0.150000
"""[1:-1]
#pre-populate names and descriptions
_CONV_FILTER_NAMES = []
_CONV_FILTER_DESC = []
for l in _CONV_FILTER_FILE_CONTENTS.split('\n'):
    if l.startswith('##'):
        _CONV_FILTER_NAMES.append(l[2:-5])
    elif l.startswith('#'):
        _CONV_FILTER_DESC.append(l[1:])
del l  # clean up namespace
_CONV_FILTER_DESC = dict(zip(_CONV_FILTER_NAMES, _CONV_FILTER_DESC))
