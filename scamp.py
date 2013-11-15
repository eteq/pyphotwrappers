from __future__ import division, print_function

from .astromatic import *

__all__ = ['Scamp']


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
