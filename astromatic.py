"""
A python module for interacting and scripting with
`AstrOmatic software <http://www.astromatic.net/>`_ tools.
"""
from __future__ import division, print_function

__all__ = ['AstromaticTool',
           'AstromaticConfiguration',
           'AstromaticError',
           'Sextractor',
           'Scamp',
           'Swarp'
          ]


class AstromaticTool(object):
    """
    A superclass for a generic astromatic tool
    """
    defaultexecname = None  # subclasses define to enable `find_execpath`

    def __init__(self, execpath=None, initialconfig=None, verbose=False):
        """
        `initialconfig` should be a string or dict.  If None, it will be
        taken from calling the tool with ``-dd``.
        """
        import os

        self.verbose = verbose
        self.cfg = None  # gets replaced below, but needed when initializing some parts

        if execpath is None:
            execpath = _which_path(self.defaultexecname)

        self.execpath = os.path.abspath(execpath)

        if initialconfig is None:
            initialconfig = self._invoke_tool(['-dd'], useconfig=False)[0]  # [0] is stdout
        self.cfg = AstromaticConfiguration(initialconfig)

    def _invoke_tool(self, arguments, validretcodes=[0], useconfig=True, showoutput=False):
        """
        Runs the tool with the given arguments, returns (stdout, stderr)

        if `useconfig` is a string, it will be treated as a filename to send the
        configuration file to.

        If not a valid return code, raises an AstromaticError with stderr as the
        second argument

        `showoutput` being True means that the return values will be None
        instead of stdout and stderr
        """
        import os
        import shlex
        import subprocess

        from tempfile import NamedTemporaryFile

        if isinstance(arguments, basestring):
            arguments = shlex.split(arguments)

        if self.cfg is None:
            inproxies = []
            outproxies = []
        else:
            inproxies, outproxies = self.cfg.get_proxies()
        allproxies = inproxies + outproxies

        try:
            #now prepare the proxy files
            for inp in inproxies:
                inp.tempfileobj = NamedTemporaryFile(delete=False)
                if self.verbose:
                    print('Using temporary file {0} for input {1}'.format(inp.tempfileobj.name, inp.configname))
                    if self.verbose == 'debug':
                        print('Contents:\n' + inp.content)
                inp.tempfileobj.write(inp.content)
                inp.tempfileobj.close()
            for outp in outproxies:
                outp.tempfileobj = NamedTemporaryFile(delete=False)
                if self.verbose:
                    print('Using temporary file {0} for output {1}'.format(outp.tempfileobj.name, outp.configname))
                # all we actually wanted was the name so just close right away
                outp.tempfileobj.close()

            #construct invocation arguments
            #has to be here because the proxies have to be in place to know where they are
            arguments = list(arguments)
            if useconfig:
                if isinstance(useconfig, basestring):
                    if self.verbose:
                        print("Writing config file to " + useconfig)
                    with open(useconfig, 'w') as f:
                        f.write(self.cfg.get_file_contents())
                    arguments.insert(0, useconfig)
                    arguments.insert(0, '-c')
                else:
                    arguments.extend(self.cfg.get_cmdline_arguments())
            arguments.insert(0, self.execpath)

            self.lastinvocation = arguments

            if showoutput:
                p = subprocess.Popen(arguments)
            else:
                p = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()
            if p.returncode not in validretcodes:
                msg = 'Running of {0} failed with retcode {1}'.format(self.execpath,
                                                                      p.returncode)
                raise AstromaticError(msg, stderr, stdout)

            for outp in outproxies:
                #get the content from the output proxies
                with open(outp.tempfileobj.name, 'r') as f:
                    outp.content = f.read()
        finally:
            #close and delete all
            for px in allproxies:
                if px.tempfileobj is not None:
                    px.tempfileobj.close()  # shouldn't be necessary, but just in case...
                    if os.path.isfile(px.tempfileobj.name):
                        os.remove(px.tempfileobj.name)
                    px.tempfileobj = None

        return stdout, stderr


class AstromaticConfiguration(object):
    """
    An object that stores astromatic configuration information (for use
    with `AstromaticTool`)

    Parameters
    ----------
    config : str or dict
        If a string and `values` is None, will be interpreted as output
        of a config file dump. Otherwise, a dict mapping names
        of items to values (comments will be empty).
    """
    _config_items = tuple()  # ensures getattr and setattr work right

    def __init__(self, config, values=None):
        self._initial_cfgstr = None
        if isinstance(config, basestring):
            self._initial_cfgstr = config
            self._parse_config_file(config)
        else:
            self._config_items = []
            self._config_settings = {}
            self._config_comments = {}
            for nm in config:
                self._config_items.append(nm)
                self._config_settings[nm] = config[nm]
                self._config_comments[nm] = ''

    def _parse_config_file(self, configstr):
        """
        REPLACES existing config
        """
        self._config_items = []
        self._config_settings = {}
        self._config_comments = {}
        for l in configstr.split('\n'):
            if not (l.startswith('#') or l.strip() == ''):
                ls = l.split('#')
                if len(ls) > 1:
                    content, comment = ls
                else:
                    content = ls[0]
                    comment = ''

                contentstrip = content.strip()
                if contentstrip == '':
                    #it's a continuation from the previous comment
                    lasti = self._config_items[-1]
                    self._config_comments[lasti] += ' ' + comment.strip()
                else:
                    contentsplit = contentstrip.split()
                    if len(contentsplit) > 1:
                        nm = contentsplit[0]
                        val = contentstrip[len(nm):].strip()
                    elif len(contentsplit) == 1:
                        nm = contentsplit[0]
                        val = ''
                    else:
                        raise ValueError('Invalid content in config file: ' + str(contentsplit))

                    self._config_items.append(nm)
                    self._config_settings[nm] = val
                    self._config_comments[nm] = comment

    @property
    def names(self):
        return tuple(self._config_items)

    @property
    def comments(self):
        return self._config_comments.copy()

    def __str__(self):
        lines = ['Astromatic configuration file:']
        for nm, val in self.get_normalized_items(acceptungenerated=True):
            lines.append((nm, val, self._config_comments[nm]))
        return '\n'.join([str(i) for i in lines])

    def __getattr__(self, name):
        if name.startswith('_') or name not in self._config_items:
            # this should always fail in the standard way
            return object.__getattribute__(self, name)
        return self._config_settings[name]

    def __setattr__(self, name, value):
        if name in self._config_items:
            self[name] = value  # got through setitem to do any special steps
        else:
            object.__setattr__(self, name, value)

    def __dir__(self):
        drs = dir(self.__class__)
        drs.extend(self.__dict__)
        drs.extend(self._config_items)
        return drs

    def __getitem__(self, key):
        return self._config_settings[key]

    def __setitem__(self, key, value):
        if key in self._config_items:
            self._config_settings[key] = value
            if hasattr(value, 'configname'):
                value.configname = key
        else:
            raise KeyError('Invalid config item name ' + str(key))

    def __len__(self):
        return len(self._config_items)

    def get_normalized_items(self, acceptungenerated=False):
        """
        Returns a list of (name, value) pairs with proxy objects
        replaced with the actual values that should get passed into the
        tool (e.g., temporary file names)
        """
        elems = []
        for iname in self._config_items:
            val = self._config_settings[iname]
            if isinstance(val, ProxyInputFile):
                if val.tempfileobj is not None:
                    elems.append((iname, val.tempfileobj.name))
                elif acceptungenerated:
                    elems.append((iname, 'PROXY INPUT FILE NOT PRESENT'))
                else:
                    raise ValueError("Item {0} is an input file but the file "
                                     "hasn't been generated!".format(iname))
            elif isinstance(val, ProxyOutputFile):
                if val.tempfileobj is not None:
                    elems.append((iname, val.tempfileobj.name))
                elif acceptungenerated:
                    elems.append((iname, 'PROXY OUTPUT FILE NOT PRESENT'))
                else:
                    raise ValueError("Item {0} is an output file but the file "
                                     "hasn't been generated!".format(iname))
            elif isinstance(val, basestring):
                elems.append((iname, val))
            else:
                raise TypeError('Invalid config item ' + str(val))
        return elems

    def get_proxies(self):
        """
        Determines and returns all the configuration items that have
        proxy files instead of normal values.

        Returns
        -------
        inproxies : list
            A list of `ProxyInputFile`s in this configuration
        outproxies : list
            A list of `ProxyOutputFile`s in this configuration
        """
        ins = []
        outs = []
        for iname in self._config_items:
            val = self._config_settings[iname]
            if isinstance(val, ProxyInputFile):
                ins.append(val)
            elif isinstance(val, ProxyOutputFile):
                outs.append(val)
        return ins, outs

    def get_cmdline_arguments(self):
        """
        Returns a list of the command line argument items needed to use
        these settings.  To get the actual command line string, do
        ``' '.join(res)`` on the return value
        """
        elems = []
        for iname, val in self.get_normalized_items():

            elems.append('-' + iname)
            elems.append(val)
        return elems

    def get_file_contents(self):
        """
        Returns a string with the contents expected for an AstrOmatic
        tool's configuration file format.
        """
        lines = []
        for iname, val in self.get_normalized_items():
            lines.append(iname + ' ' + val)
        return '\n'.join(lines)


class ProxyInputFile(object):
    """
    A stand-in for an input file - a temp file will be created during invokation
    of the tool, and then deleted.  The content comes from this object.
    """
    def __init__(self, content):
        self.content = content
        self.configname = None
        self.tempfileobj = None


class ProxyOutputFile(object):
    """
    A stand-in for an output file - a temp file will be created during invokation
    of the tool, and then deleted.  The `content` attribute of this object will
    be populated
    """
    def __init__(self):
        self.content = None
        self.configname = None
        self.tempfileobj = None

    def read_ascii(self, *args, **kwargs):
        """
        Attempt to read the contents using astropy.io.ascii

        `args` and `kwargs` are passed into `read`
        """
        from astropy.io import ascii
        return ascii.read(self.content, *args, **kwargs)


#<------------------------------Specific tools--------------------------------->
class Sextractor(AstromaticTool):
    """
    Driver class for scripting Sextractor

    Parameters
    ----------
    execpath : None or str
        Path to executable or None to search for it
    autofunpack : bool
        If True, will automatically use ``funpack`` to unpack input files that
        end in ``.fz`` (SExtractor can't handle fits compression).  Can be a
        string, in which case it points to the executable for funpack.
    """
    defaultexecname = 'sex'

    def __init__(self, execpath=None, autofunpack=True):
        super(Sextractor, self).__init__(execpath)

        self._parse_outputs(self._invoke_tool(['-dp'])[0])
        self.reset_outputs()
        self.choose_conv_filter('default')

        self.cfg.PARAMETERS_NAME = ProxyInputFile('PLACEHOLDER: WILL BE POPULATED BY Sextractor CLASS')

        self.autofunpack = autofunpack

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
            with open(self.cfg.CATALOG_NAME, 'rb') as f:
                content = f.read()

        if astable:
            lcattype = self.cfg.CATALOG_TYPE.lower()
            if 'votable' in lcattype:
                from astropy.io import votable
                from io import BytesIO
                return votable.parse(BytesIO(content))
            elif 'ascii' in lcattype:
                return ascii.read(content, names=self.outputs)
            elif 'fits' in lcattype:
                from astropy.io import fits
                return fits.HDUList.fromstring(content)[2].data
        else:
            return content

    def sextract_single(self, img, proxycat=False):
        """
        Run sextractor in single output mode

        Parameters
        ----------
        img : str
            The input file
        proxycat : bool
            If True, will overwrite `CATALOG_NAME` with an output proxy, so
            the catalog will only be saved there.  It can be accessed later
            with `self.get_output()`.
        """
        import os

        funimg = self._try_funpack(img)
        try:
            self._invoke_tool([img if funimg is None else funimg], showoutput=True)
            self.lastimg = img
        finally:
            if funimg is not None:
                if os.path.isfile(funimg):
                    os.remove(funimg)

    def sextract_double(self, masterimg, analysisimg, proxycat=False):
        import os

        masterfunimg = self._try_funpack(masterimg)
        analysisfunimg = self._try_funpack(analysisimg)
        try:
            self._invoke_tool([masterimg if masterfunimg is None else masterfunimg,
                               analysisimg if analysisfunimg is None else analysisfunimg],
                              showoutput=True)
        finally:
            if analysisfunimg is not None:
                if os.path.isfile(analysisfunimg):
                    os.remove(analysisfunimg)
            if masterfunimg is not None:
                if os.path.isfile(masterfunimg):
                    os.remove(masterfunimg)

        self.lastimg = analysisimg
        self.lastmaster = masterimg

    def _try_funpack(self, fn):
        """
        runs funpack if necessary.

        Returns a (closed) temporary file object, which needs to be manually
        deleted when no longer needed, or None if funpack is unnecessary
        """
        import os
        import time
        import tempfile
        import subprocess

        if fn.endswith('.fz'):
            if self.autofunpack is True:
                self.autofunpack = _which_path('funpack')

            if fn.endswith('.fz'):
                tfn = os.path.split(fn[:-3])[1]
            else:
                tfn = os.path.split(fn)[1]
            tfn = os.path.join(tempfile.gettempdir(), tempfile.gettempprefix() + tfn)
            if os.path.exists(tfn):
                os.remove(tfn)

            if self.verbose:
                print('Running funpack to extract file {0} to {1}'.format(fn, tfn))
            sttime = time.time()
            retcode = subprocess.call([self.autofunpack, '-O', tfn, fn])
            etime = time.time()
            if retcode != 0:
                raise OSError('funpack failed with return code ' + str(retcode))
            if self.verbose:
                print('Funpack finished in {0} secs'.format(etime - sttime))

            return tfn
        else:
            # technically unnecessary, but useful for clarity's sake
            return None

    def ds9_mark(self, sizekey='FLUX_RADIUS', ds9=None, doload=True, clearmarks=True):
        """
        Mark the sextracted outputs on ds9.

        Parameters
        ----------
        sizekey : str or number
            The name of the column to use as the size of the circles or a
            number for them all to be the same.  If key is missing, default=5.
        ds9 : None or pysao.ds9 instance
            if None, a new DS9 will be started, otherwise the instance to use
        doload : bool
            If True, loads the file.
        clearmarks
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
        if currfn != self.lastimg:
            if self.verbose:
                print("Current filename {0} does not match {1}.  Reloading.".format(currfn, self.lastimg))
            ds9.load_fits(self.lastimg)
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

        ds9.mark(x, y, sz)

        return ds9


class Scamp(AstromaticTool):
    defaultexecname = 'scamp'

    def __init__(self, execpath=None):
        super(Scamp, self).__init__(execpath)

    def scamp_catalogs(self, catfns):
        """
        Runs scamp on the given `catfns`
        """
        if isinstance(catfns, basestring):
            catfns = [catfns]
        self._invoke_tool(catfns, showoutput=True)

    def set_ahead_from_dict(self, dct):
        headlns = []
        for k, v in dct.iteritems():
            if len(k) > 8:
                raise ValueError('Keys must be <= 8 chars - "{0}" is not'.format(k))
            keystr = k.upper() + ((8 - len(k)) * ' ')
            vstr = ("'" + v + "'") if isinstance(v, basestring) else str(v)
            headlns.append(keystr + '= ' + vstr)
        self.cfg.AHEADER_GLOBAL = ProxyInputFile('\n'.join(headlns) + '\n')


class Swarp(AstromaticTool):
    defaultexecname = 'swarp'

    def __init__(self, execpath=None):
        super(Swarp, self).__init__(execpath)


class AstromaticError(Exception):
    pass


def _which_path(execname):
    """
    Returns either the path to `execname` or None if it can't be found
    """
    import subprocess
    from warnings import warn

    try:
        p = subprocess.Popen(['which', execname], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        sout, serr = p.communicate()
        if p.returncode != 0:
            warn('"which" failed to find the executable {0}, is it '
                 'installed?' + execname)
        else:
            return sout.strip()
    except OSError as e:
        warn('Could not find "which" to find executable location. '
             'Continuing, but you will need to set `execpath` manually.'
             ' Error:\n' + str(e))
    return None


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
