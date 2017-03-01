# This module provides a compatibility layer between Python 2 and 3.

import sys

using_py3 = sys.version_info[0] >= 3

####################
# Built-in functions that were renamed in Python 3

if using_py3:
    input = input
else:
    input = raw_input


####################
# Standard modules that were renamed in Python 3

if using_py3:
    import configparser
    import io
    from queue import Queue, Empty
else:
    import ConfigParser as configparser
    import StringIO as io
    from Queue import Queue, Empty

