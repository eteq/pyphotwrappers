"""
A python module for interacting and scripting with DAOphot command-line tools.

Note that this is a work-in-progess and not yet functional
"""
from __future__ import division, print_function

__all__ = ['DaophotBase', 'Daophot']


class DaophotBase(object):
    """
    A superclass for running various DAOphot tools
    """
    defaultexecname = None  # subclasses define to enable `find_execpath`

    _config_items = tuple()  # ensures getattr and setattr work right

    def __init__(self, execpath=None, initialconfig=None, verbose=False):
        """
        `initialconfig` should be a string
        """
        import os
        import subprocess
        from warnings import warn

        self.verbose = verbose

        if execpath is None:
            try:
                p = subprocess.Popen(['which', self.defaultexecname], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                sout, serr = p.communicate()
                if p.returncode != 0:
                    warn('"which" failed to find the executable {0}, is it '
                         'installed?' + self.defaultexecname)

            except OSError as e:
                warn('Could not find "which" to find executable location. '
                     'Continuing, but you will need to set `execpath` manually.'
                     ' Error:\n' + str(e))
            execpath = sout.strip()

        self.execpath = os.path.abspath(execpath)


#<------------------------------Specific tools--------------------------------->
class Daophot(DaophotBase):
    defaultexecname = 'daophot'

    def __init__(self, execpath=None):
        super(Daophot, self).__init__(execpath)
