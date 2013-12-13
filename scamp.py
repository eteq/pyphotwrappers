from __future__ import division, print_function

from .astromatic import *
from . import utils

__all__ = ['Scamp']


class Scamp(AstromaticTool):
    """
    Driver class for scripting Scamp

    Parameters
    ----------
    execpath : None or str, optional
        Path to executable or None to search for it
    renameoutputs : str or None, optional
        If present, indicates that the output files should be renamed to the
        provided string pattern.  The string can include '{path}', '{fn}',
        '{input}', meaning the path and name from the configuration, and the
        base name of the input file.
    checkplotpath : str, optional
        Path at which to move any generated check plots
    pstopdf : bool or str, optional
        If this evaluates to True, will convert any checkplots to pdf. if a
        string, it will be interpreted as an executable path to `ps2pdf` or
        `pstopdf`.
    overwrite : bool, optional
        If True, will overwrite the output header files even if they already
        exist.
    verbose : bool, optional
        If True, diagnostic information will be printed while running.
    """
    defaultexecname = 'scamp'

    def __init__(self, execpath=None, renameoutputs=None, checkplotpath=None,
                 pstopdf=True, overwrite=True, verbose=False):
        super(Scamp, self).__init__(execpath, verbose=verbose)
        self.renameoutputs = renameoutputs
        self.checkplotpath = checkplotpath
        self.pstopdf = pstopdf
        self.overwrite = overwrite

    def scamp_catalogs(self, catfns):
        """
        Runs scamp on the given `catfns`
        """
        from warnings import warn

        if isinstance(catfns, basestring):
            catfns = [catfns]

        if not self.overwrite:
            prevoutputheads = self._check_output_exists(catfns)
            if prevoutputheads:
                if self.verbose:
                    print("Outputs {0} already exist, not running Scamp".format(prevoutputheads))
                return prevoutputheads

        initialcpdev = self.cfg.CHECKPLOT_DEV
        try:
            if self.pstopdf and self._CP_DEV_TO_EXT[self.cfg.CHECKPLOT_DEV] != '.ps':
                warn('CHECKPLOT_DEV is not a postscript output, but ps->pdf '
                     'conversion was requested.  Changing to "PSC".')
                self.cfg.CHECKPLOT_DEV = 'PSC'
            self._invoke_tool(catfns, showoutput=True)
        finally:
            self.cfg.CHECKPLOT_DEV = initialcpdev

        self.lastcats = catfns

        if self.renameoutputs:
            self._reprocess_outputs()

        return self._check_output_exists(catfns)

    def set_ahead_from_dict(self, dct):
        headlns = []
        for k, v in dct.iteritems():
            if len(k) > 8:
                raise ValueError('Keys must be <= 8 chars - "{0}" is not'.format(k))
            keystr = k.upper() + ((8 - len(k)) * ' ')
            vstr = ("'" + v + "'") if isinstance(v, basestring) else str(v)
            headlns.append(keystr + '= ' + vstr)
        self.cfg.AHEADER_GLOBAL = ProxyInputFile('\n'.join(headlns) + '\n')

    _CP_DEV_TO_EXT = {'NULL': None,
                      'XWIN': None,
                      'TK': None,
                      'PLMETA': '.plm',
                      'PS': '.ps',
                      'PSC': '.ps',
                      'XFIG': '.fig',
                      'PNG': '.png',
                      'JPEG': '.jpg',
                      'PSTEX': '.ps'
                     }  # used in get_reprocessed_output_fns

    def get_reprocessed_output_fns(self, mkdirs=False):
        """
        Gets the names that the scamp outputs will get mapped to if
        `renameoutputs` is True.

        Parameters
        ----------
        mkdirs : bool, optional
            If True, any directories necessary will be created

        Returns
        -------
        xmlmap : dict
            Mapping of XML file names as written by scamp mapped to new names.
        cppatmap : dict
            Mapping of checkplot file *patterns* as written by scamp to new
            patterns.  These are patterns because scamp sometimes makes multiple
            checkplots.
        """
        import os

        lastcat = self.lastcats[0]

        input_ = os.path.split(lastcat)[1]
        for ext in ['.cat', '.ldac', '.dat', '.fits']:
            if ext in input_:
                input_ = input_.split(ext)[0]
                break

        #XML output
        oldxmlfn = self.cfg.XML_NAME
        path, fn = os.path.split(oldxmlfn)
        newxmlfn = self.renameoutputs.format(
            path=path + ('' if path.endswith(os.path.sep) or path == '' else os.path.sep),
            fn=fn, input=input_)
        xmlmap = {oldxmlfn: newxmlfn}
        xmldir = os.path.split(newxmlfn)[0]
        if mkdirs and xmldir and not os.path.isdir(xmldir):
            if self.verbose:
                print('Making XML dir "{0}"'.format(xmldir))
            utils.nested_mkdir(xmldir)

        cppatmap = {}
        cpext = self._CP_DEV_TO_EXT[self.cfg.CHECKPLOT_DEV]
        if cpext is None:
            # means this is a type that doesn't generate files
            return xmlmap, cppatmap
        for cpfn in self.cfg.CHECKPLOT_NAME.split(','):
            cpfn = cpfn.strip() + cpext
            path, fn = os.path.split(cpfn)

            #rename checkplot
            if self.checkplotpath:
                path = self.checkplotpath

            #rename if pstopdf is true
            if self.pstopdf:
                fn = cpfn[:-3] + '.pdf'

            basenfn, next = os.path.splitext(self.renameoutputs.format(
                path=path + ('' if path.endswith(os.path.sep) or path == '' else os.path.sep),
                fn=fn, input=input_))
            baseofn, oext = os.path.splitext(cpfn)
            cppatmap[baseofn + '_*' + oext] = basenfn + '_*' + next

            cpdir = os.path.split(basenfn)[0]
            if mkdirs and cpdir and not os.path.isdir(cpdir):
                if self.verbose:
                    print('Making check plot dir "{0}"'.format(cpdir))
                utils.nested_mkdir(cpdir)

        return xmlmap, cppatmap

    def _reprocess_outputs(self):
        import os
        import re
        from glob import glob
        from shutil import move

        xmlmap, cppatmap = self.get_reprocessed_output_fns(mkdirs=True)

        for ofn, nfn in xmlmap.iteritems():
            if os.path.isfile(ofn):
                if self.verbose:
                    print("Moving XML file {0} to {1}".format(ofn, nfn))
                move(ofn, nfn)

        #find all the actual check plots based on the patterns
        cpmap = {}
        for opat, npat in cppatmap.iteritems():
            rex = re.compile(opat.replace('*', '(.*?)'))
            for fn in glob(opat):
                cpmap[fn] = npat.replace('*', rex.match(fn).group(1))

        for ofn, nfn in cpmap.iteritems():
            if nfn.endswith('.pdf'):
                if self._do_pstopdf(ofn, nfn):
                    os.remove(ofn)
                    continue  # instead of moving ps, just remove it
                else:
                    #_do_pstopdf returns None/False only if pstopdf missing
                    nfn = nfn[:-4] + '.ps'

            if self.verbose:
                print("Moving check plot {0} to {1}".format(ofn, nfn))
            move(ofn, nfn)

    def _check_output_exists(self, catfns):
        import os

        existingheads = []

        for catfn in catfns:
            splfn = catfn.split('.')
            if len(splfn) > 0:
                catbase = '.'.join(splfn[:-1])
            else:
                catbase = splfn[0]
            headfn = catbase + '.head'

            if os.path.exists(headfn):
                existingheads.append(headfn)

        return existingheads

    def _do_pstopdf(self, psfn, newfn):
        import subprocess
        from warnings import warn

        if not getattr(self, '_pstopdfexec', None):
            #try two different common ps to pdf converters
            self._pstopdfexec = utils.which_path('ps2pdf')
            if self._pstopdfexec is None:
                self._pstopdfexec = utils.which_path('pstopdf')

        if self._pstopdfexec is None:
            warn('Could not find any sort of ps->pdf converter! Cannot output pdf checkplots.')
        else:
            if self.verbose:
                print("Converting check plot {0} to {1}".format(psfn, newfn))
            if 'pstopdf' in self._pstopdfexec:
                subprocess.check_call([self._pstopdfexec, psfn, '-o', newfn])
            else:  # ps2pdf doesn't need the -o - it's just ``ps2pdf infn outfn``
                subprocess.check_call([self._pstopdfexec, psfn, newfn])
        return self._pstopdfexec  # None if it failed
