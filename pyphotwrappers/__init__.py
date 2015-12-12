"""
Python wrappers for photometry tools
"""

# Affiliated packages may add whatever they like to this file, but
# should keep this content at the top.
# ----------------------------------------------------------------------------
from ._astropy_init import *
# ----------------------------------------------------------------------------

# For egg_info test builds to pass, put package imports here.
if not _ASTROPY_SETUP_:
	from .sextractor import *
	from .scamp import *
	from .swarp import *
	from .daophot import *
