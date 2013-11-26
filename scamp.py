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
        if isinstance(catfns, basestring):
            catfns = [catfns]
        self._invoke_tool(catfns, showoutput=True)
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
        newxmlfn = self.renameoutputs.format(path=path, fn=fn, input=input_)
        xmlmap = {oldxmlfn: newxmlfn}

        #rename check plots if present
        if self.checkplotpath:
            checkplotpath = self.checkplotpath + ('' if checkplotpath.endswith(os.sep) else os.sep)
        else:
            checkplotpath = None

        cpmap = {}
        for cpfn in self.cfg.CHECKPLOT_NAME.split(','):
            cpfn = cpfn.strip() + '.ps'
            path, fn = os.path.split(cpfn)
            if self.pstopdf:
                fn = cpfn[:-3] + '.pdf'
            cpmap[cpfn] = self.renameoutputs.format(
                path=checkplotpath if checkplotpath else path,
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
                if self.verbose:
                    print("Converting check plot {0} to {1}".format(ofn, nfn))
                self._do_pstopdf(ofn, nfn)
                os.path.remove(ofn)
            else:
                if self.verbose:
                    print("Moving check plot {0} to {1}".format(cpfn, newfn))
                move(ofn, nfn)

    def _do_pstopdf(self, psfn, newfn):
        raise NotImplementedError
