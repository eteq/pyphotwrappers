def which_path(execname):
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


def nested_mkdir(dirnm):
    """
    makes a directory and all those leading up to it if they don't exist
    """
    import os

    dirsmade = []
    segments = dirnm.split(os.sep)
    for i in range(len(segments)):
        dirnm = os.sep.join(segments[:(i + 1)])
        if not os.path.isdir(dirnm):
            os.mkdir(dirnm)
            dirsmade.append(dirnm)
    return dirsmade

# used by _try_decompress in Sextractor and Swarp
fitsextension_to_decompresser = {'.fz': 'funpack', '.gz': 'gunzip'}
