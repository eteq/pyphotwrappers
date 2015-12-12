"""
A python module for interacting and scripting with
`AstrOmatic software <http://www.astromatic.net/>`_ tools.
Specific tools are in their own modules.
"""
from __future__ import division, print_function

import collections

__all__ = ['AstromaticTool',
           'AstromaticConfiguration',
           'AstromaticComments',
           'AstromaticError',
           'ProxyInputFile',
           'ProxyOutputFile'
          ]


class AstromaticTool(object):
    """
    A superclass for a generic astromatic tool
    """
    defaultexecname = None  # subclasses define to enable `find_execpath`

    def __init__(self, execpath=None, initialconfig=None, verbose=False):
        """
        `initialconfig` should be a string or dict.  If None, it will be
        taken from calling the tool with ``-dd``.
        """
        import os

        from .utils import which_path

        self.verbose = verbose
        self.cfg = None  # gets replaced below, but needed when initializing some parts

        if execpath is None:
            execpath = which_path(self.defaultexecname)

        self.execpath = os.path.abspath(execpath)

        if initialconfig is None:
            initialconfig = self._invoke_tool(['-dd'], useconfig=False)[0]  # [0] is stdout
        self.cfg = AstromaticConfiguration(initialconfig)

    def _invoke_tool(self, arguments, validretcodes=[0], useconfig=True, showoutput=False):
        """
        Runs the tool with the given arguments, returns (stdout, stderr)

        if `useconfig` is a string, it will be treated as a filename to send the
        configuration file to.

        If not a valid return code, raises an AstromaticError with stderr as the
        second argument

        `showoutput` being True means that the return values will be None
        instead of stdout and stderr
        """
        import os
        import shlex
        import subprocess

        from tempfile import NamedTemporaryFile

        if isinstance(arguments, basestring):
            arguments = shlex.split(arguments)

        if self.cfg is None:
            inproxies = []
            outproxies = []
        else:
            inproxies, outproxies = self.cfg.get_proxies()
        allproxies = inproxies + outproxies

        try:
            #now prepare the proxy files
            for inp in inproxies:
                inp.tempfileobj = NamedTemporaryFile(delete=False)
                if self.verbose:
                    print('Using temporary file {0} for input {1}'.format(inp.tempfileobj.name, inp.configname))
                    if self.verbose == 'debug':
                        print('Contents:\n' + inp.content)
                inp.tempfileobj.write(inp.content)
                inp.tempfileobj.close()
            for outp in outproxies:
                outp.tempfileobj = NamedTemporaryFile(delete=False)
                if self.verbose:
                    print('Using temporary file {0} for output {1}'.format(outp.tempfileobj.name, outp.configname))
                # all we actually wanted was the name so just close right away
                outp.tempfileobj.close()

            #construct invocation arguments
            #has to be here because the proxies have to be in place to know where they are
            arguments = list(arguments)
            if useconfig:
                if isinstance(useconfig, basestring):
                    if self.verbose:
                        print("Writing config file to " + useconfig)
                    with open(useconfig, 'w') as f:
                        f.write(self.cfg.get_file_contents())
                    arguments.insert(0, useconfig)
                    arguments.insert(0, '-c')
                else:
                    arguments.extend(self.cfg.get_cmdline_arguments())
            arguments.insert(0, self.execpath)

            self.lastinvocation = arguments

            if showoutput:
                p = subprocess.Popen(arguments)
            else:
                p = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()
            if p.returncode not in validretcodes:
                msg = 'Running of {0} failed with retcode {1}'.format(self.execpath,
                                                                      p.returncode)
                raise AstromaticError(msg, stderr, stdout)

            for outp in outproxies:
                #get the content from the output proxies
                with open(outp.tempfileobj.name, 'r') as f:
                    outp.content = f.read()
        finally:
            #close and delete all
            for px in allproxies:
                if px.tempfileobj is not None:
                    px.tempfileobj.close()  # shouldn't be necessary, but just in case...
                    if os.path.isfile(px.tempfileobj.name):
                        os.remove(px.tempfileobj.name)
                    px.tempfileobj = None

        return stdout, stderr


class AstromaticConfiguration(object):
    """
    An object that stores astromatic configuration information (for use
    with `AstromaticTool`)

    Parameters
    ----------
    config : str or dict
        If a string and `values` is None, will be interpreted as output
        of a config file dump. Otherwise, a dict mapping names
        of items to values (comments will be empty).
    """
    _config_items = tuple()  # ensures getattr and setattr work right

    def __init__(self, config, values=None):
        self._initial_cfgstr = None
        if isinstance(config, basestring):
            self._initial_cfgstr = config
            self._parse_config_file(config)
        else:
            self._config_items = []
            self._config_settings = {}
            comments_dict = {}
            for nm in config:
                self._config_items.append(nm)
                self._config_settings[nm] = config[nm]
                comments_dict[nm] = ''
            self._comments = AstromaticComments(comments_dict)

    def _parse_config_file(self, configstr):
        """
        REPLACES existing config
        """
        self._config_items = []
        self._config_settings = {}
        comments_dict = {}
        for l in configstr.split('\n'):
            if not (l.startswith('#') or l.strip() == ''):
                ls = l.split('#')
                if len(ls) > 1:
                    content, comment = ls
                else:
                    content = ls[0]
                    comment = ''

                contentstrip = content.strip()
                if contentstrip == '':
                    #it's a continuation from the previous comment
                    lasti = self._config_items[-1]
                    comments_dict[lasti] += ' ' + comment.strip()
                else:
                    contentsplit = contentstrip.split()
                    if len(contentsplit) > 1:
                        nm = contentsplit[0]
                        val = contentstrip[len(nm):].strip()
                    elif len(contentsplit) == 1:
                        nm = contentsplit[0]
                        val = ''
                    else:
                        raise ValueError('Invalid content in config file: ' + str(contentsplit))

                    self._config_items.append(nm)
                    self._config_settings[nm] = val
                    comments_dict[nm] = comment
        self._comments = AstromaticComments(comments_dict)

    @property
    def names(self):
        return tuple(self._config_items)

    @property
    def comments(self):
        return self._comments

    def __str__(self):
        lines = ['Astromatic configuration file:']
        for nm, val in self.get_normalized_items(acceptungenerated=True):
            lines.append((nm, val, self.comments[nm]))
        return '\n'.join([str(i) for i in lines])

    def __getattr__(self, name):
        if name.startswith('_') or name not in self._config_items:
            # this should always fail in the standard way
            return object.__getattribute__(self, name)
        return self._config_settings[name]

    def __setattr__(self, name, value):
        if name in self._config_items:
            self[name] = value  # got through setitem to do any special steps
        else:
            object.__setattr__(self, name, value)

    def __dir__(self):
        drs = dir(self.__class__)
        drs.extend(self.__dict__)
        drs.extend(self._config_items)
        return drs

    def __getitem__(self, key):
        return self._config_settings[key]

    def __setitem__(self, key, value):
        if key in self._config_items:
            self._config_settings[key] = value
            if hasattr(value, 'configname'):
                value.configname = key
        else:
            raise KeyError('Invalid config item name ' + str(key))

    def __len__(self):
        return len(self._config_items)

    def get_normalized_items(self, acceptungenerated=False):
        """
        Returns a list of (name, value) pairs with proxy objects
        replaced with the actual values that should get passed into the
        tool (e.g., temporary file names)
        """
        elems = []
        for iname in self._config_items:
            val = self._config_settings[iname]
            if isinstance(val, ProxyInputFile):
                if val.tempfileobj is not None:
                    elems.append((iname, val.tempfileobj.name))
                elif acceptungenerated:
                    elems.append((iname, 'PROXY INPUT FILE NOT PRESENT'))
                else:
                    raise ValueError("Item {0} is an input file but the file "
                                     "hasn't been generated!".format(iname))
            elif isinstance(val, ProxyOutputFile):
                if val.tempfileobj is not None:
                    elems.append((iname, val.tempfileobj.name))
                elif acceptungenerated:
                    elems.append((iname, 'PROXY OUTPUT FILE NOT PRESENT'))
                else:
                    raise ValueError("Item {0} is an output file but the file "
                                     "hasn't been generated!".format(iname))
            elif isinstance(val, basestring):
                elems.append((iname, val))
            else:
                raise TypeError('Invalid config item ' + str(val))
        return elems

    def get_proxies(self):
        """
        Determines and returns all the configuration items that have
        proxy files instead of normal values.

        Returns
        -------
        inproxies : list
            A list of `ProxyInputFile`s in this configuration
        outproxies : list
            A list of `ProxyOutputFile`s in this configuration
        """
        ins = []
        outs = []
        for iname in self._config_items:
            val = self._config_settings[iname]
            if isinstance(val, ProxyInputFile):
                ins.append(val)
            elif isinstance(val, ProxyOutputFile):
                outs.append(val)
        return ins, outs

    def get_cmdline_arguments(self, acceptungenerated=False):
        """
        Returns a list of the command line argument items needed to use
        these settings.  To get the actual command line string, do
        ``' '.join(res)`` on the return value
        """
        elems = []
        for iname, val in self.get_normalized_items(acceptungenerated=acceptungenerated):
            elems.append('-' + iname)
            elems.append(val)
        return elems

    def get_file_contents(self, acceptungenerated=False, outfn=None):
        """
        Returns a string with the contents expected for an AstrOmatic
        tool's configuration file format.

        Parameters
        ----------
        acceptungenerated : bool, optional
            If True, the file will be generated even if proxy files are missing
            (they will be set to empty strings)
        outfn : str, optional
            If given, the configuration contents will be written to this file
            name.

        Returns
        -------
        filecontents : str
            The contents of a configuration file matching this object.

        """
        lines = []
        for iname, val in self.get_normalized_items(acceptungenerated=acceptungenerated):
            lines.append(iname + ' ' + val)

        contents = '\n'.join(lines)

        if outfn:
            with open(outfn, 'w') as f:
                f.write(contents)

        return contents


class AstromaticComments(collections.Mapping):
    """
    A very simple class for storing comments that allows attribute-style *OR*
    dict-style access
    """
    def __init__(self, comment_dict):
        self._comment_dict = comment_dict

    def __getattr__(self, key):
        if key.startswith('_') or key not in self._comment_dict:
            # this should always fail in the standard way
            return object.__getattribute__(self, key)
        return self._comment_dict[key]

    def __setattr__(self, key, value):
        if key.startswith('_') or key not in self._comment_dict:
            object.__setattr__(self, key, value)
        else:
            raise AttributeError('Cannot change the value of a config comment')

    def __dir__(self):
        drs = dir(self.__class__)
        drs.extend(self.__dict__)
        drs.extend(self._comment_dict)
        return drs

    def __getitem__(self, key):
        return self._comment_dict[key]

    def __len__(self):
        return len(self._comment_dict)

    def __iter__(self):
        return iter(self._comment_dict)

    def __eq__(self, obj):
        return self._comment_dict == obj


class ProxyInputFile(object):
    """
    A stand-in for an input file - a temp file will be created during invokation
    of the tool, and then deleted.  The content comes from this object.
    """
    def __init__(self, content):
        self.content = content
        self.configname = None
        self.tempfileobj = None


class ProxyOutputFile(object):
    """
    A stand-in for an output file - a temp file will be created during invokation
    of the tool, and then deleted.  The `content` attribute of this object will
    be populated
    """
    def __init__(self):
        self.content = None
        self.configname = None
        self.tempfileobj = None

    def read_ascii(self, *args, **kwargs):
        """
        Attempt to read the contents using astropy.io.ascii

        `args` and `kwargs` are passed into `read`
        """
        from astropy.io import ascii
        return ascii.read(self.content, *args, **kwargs)


class AstromaticError(Exception):
    pass
