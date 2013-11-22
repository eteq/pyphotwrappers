from __future__ import division, print_function

from .astromatic import *

__all__ = ['Scamp']


class Scamp(AstromaticTool):
    defaultexecname = 'scamp'

    def __init__(self, execpath=None, renameoutputs=None, checkplotpath=None):
        super(Scamp, self).__init__(execpath)
        self.renameoutputs = renameoutputs
        self.checkplotpath = checkplotpath

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

    def _reprocess_outputs(self):
        import os
        from shutil import move

        lastcat = self.lastcats[0]

        input_ = os.path.split(inputfn)[1]
        for ext in ['.cat', '.ldac', '.dat', '.fits']:
            if ext in input_:
                input_ = input_.split(ext)[0]
                break

        #rename XML output if present
        if os.path.isfile(self.cfg.XML_NAME):
            path, fn = os.path.split(self.cfg.XML_NAME)
            newfn = self.renameoutputs.format(path=path, fn=fn, input=input_)
            move(self.cfg.XML_NAME, newfn)

        #rename check plots if present
        if self.checkplotpath:
            checkplotpath = self.checkplotpath + ('' if checkplotpath.endswith(os.sep) else os.sep)
        else:
            checkplotpath = None
        for cimgfn in self.cfg.CHECKPLOT_NAME.split(','):
            cimgfn = cimgfn.strip() + '.ps'
            if os.path.isfile(cimgfn):
                path, fn = os.path.split(cimgfn)
                if checkplotpath:
                    path = checkplotpath
                newfn = self.renameoutputs.format(path=path, fn=fn, input=input_)

                if self.pstopdf:
                    self._do_pstopdf(cimgfn, newfn)
                    os.path.remove(cimgfn)
                else:
                    move(cimgfn, newfn)

    def _do_pstopdf(self, psfn, newfn):
        raise NotImplementedError
