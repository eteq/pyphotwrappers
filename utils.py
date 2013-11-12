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
