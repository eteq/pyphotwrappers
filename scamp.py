from __future__ import division, print_function

from .astromatic import *

__all__ = ['Scamp']


class Scamp(AstromaticTool):
    defaultexecname = 'scamp'

    def __init__(self, execpath=None, renameoutputs=None, checkplotpath=None,
                 pstopdf=True, verbose=False):
        super(Scamp, self).__init__(execpath, verbose=verbose)
        self.renameoutputs = renameoutputs
        self.checkplotpath = checkplotpath
        self.pstopdf = pstopdf

    def scamp_catalogs(self, catfns):
        """
        Runs scamp on the given `catfns`
        """
        from warnings import warn

        if isinstance(catfns, basestring):
            catfns = [catfns]

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

    def get_reprocessed_output_fns(self):
        """
        Gets the names that the scamp outputs will get mapped to if
        `renameoutputs` is True.

        Returns
        -------
        xmlmap : dict
            Mapping of XML file names as written by scamp mapped to new names.
        cpmap : dict
            Mapping of checkplot file names as written by scamp to new names.
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

        cpmap = {}
        cpext = self._CP_DEV_TO_EXT[self.cfg.CHECKPLOT_DEV]
        if cpext is None:
            # means this is a type that doesn't generate files
            return xmlmap, cpmap
        for cpfn in self.cfg.CHECKPLOT_NAME.split(','):
            cpfn = cpfn.strip() + cpext
            path, fn = os.path.split(cpfn)

            #rename checkplot
            if self.checkplotpath:
                path = self.checkplotpath

            #rename if pstopdf is true
            if self.pstopdf:
                fn = cpfn[:-3] + '.pdf'

            cpmap[cpfn] = self.renameoutputs.format(
                path=path + ('' if path.endswith(os.path.sep) or path == '' else os.path.sep),
                fn=fn, input=input_)

        return xmlmap, cpmap

    def _reprocess_outputs(self):
        import os
        from shutil import move

        xmlmap, cpmap = self.get_reprocessed_output_fns()

        for ofn, nfn in xmlmap.iteritems():
            if os.path.isfile(ofn):
                if self.verbose:
                    print("Moving XML file {0} to {1}".format(ofn, nfn))
                move(ofn, nfn)

        for ofn, nfn in cpmap.iteritems():
            if nfn.endswith('.pdf'):
                self._do_pstopdf(ofn, nfn)
                os.path.remove(ofn)
            else:
                if self.verbose:
                    print("Moving check plot {0} to {1}".format(ofn, nfn))
                move(ofn, nfn)

    def _do_pstopdf(self, psfn, newfn):
        import subprocess
        from .utils import which_path

        if not getattr(self, '_pstopdfexec', None):
            self._pstopdfexec = which_path('pstopdf')


        if self.verbose:
            print("Converting check plot {0} to {1}".format(psfn, newfn))
        subprocess.check_call([self._pstopdfexec, psfn, '-o', newfn])
