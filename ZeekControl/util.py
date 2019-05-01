import os
import errno

from ZeekControl import config


# 'src' is the file to which the link will point, and 'dst' is the link to make
def force_symlink(src, dst):
    try:
        os.symlink(src, dst)
    except OSError as e:
        if e.errno == errno.EEXIST:
            os.remove(dst)
            os.symlink(src, dst)
        else:
            raise

# Returns an IP address string suitable for embedding in a Zeek script,
# for IPv6 colon-hexadecimal address strings, that means surrounding it
# with square brackets.
def format_zeek_addr(addr):
    if ":" not in addr:
        return addr
    else:
        return "[%s]" % addr

# Returns an IP prefix string suitable for embedding in a Zeek script,
# for IPv6 colon-hexadecimal prefix strings, that means surrounding the
# IP address part with square brackets.
def format_zeek_prefix(prefix):
    if ":" not in prefix:
        return prefix
    else:
        parts = prefix.split("/")
        return "[%s]/%s" % (parts[0], parts[1])

# Returns an IP address string suitable for use with rsync, which requires
# encasing IPv6 addresses in square brackets, and some shells may require
# quoting the brackets.
def format_rsync_addr(addr):
    if ":" not in addr:
        return addr
    else:
        return "'[%s]'" % addr

# Convert a number into a string with a unit (e.g., 1024 into "1K").
def number_unit_str(num):
    units = (("G", 1024*1024*1024), ("M", 1024*1024), ("K", 1024))
    for (unit, factor) in units:
        if num >= factor:
            return "%3.0f%s" % (num / factor, unit)
    return " %3.0f" % (num)

