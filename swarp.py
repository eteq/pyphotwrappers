from __future__ import division, print_function

from .astromatic import *

__all__ = ['Swarp']


class Swarp(AstromaticTool):
    defaultexecname = 'swarp'

    def __init__(self, execpath=None):
        super(Swarp, self).__init__(execpath)

    def swarp_images(self, imgs):
        """
        Runs swarp on the given `imgs`
        """
        if isinstance(imgs, basestring):
            imgs = [imgs]
        self._invoke_tool(imgs, showoutput=True)
