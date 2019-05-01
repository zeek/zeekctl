# ZeekControl exceptions.
#
# These are the exceptions that are expected to be raised under predictable
# circumstances (such as bad user input, or an invalid configuration).  When
# these are raised, a text message explaining the problem should be provided.
# Therefore, these should be caught to avoid seeing a stack trace (which
# provides no new information in these cases).  However, standard Python
# exceptions are not expected to occur, so if one is raised a stack trace
# can provide valuable information on the source of the problem.

class ZeekControlError(Exception):
    """This is the base class for ZeekControl exceptions."""

class LockError(ZeekControlError):
    """Indicates that ZeekControl was unable to obtain a lock."""

class RuntimeEnvironmentError(ZeekControlError):
    """Indicates an error in the runtime environment (e.g. running as wrong
    user, or some files/directories have wrong permissions or location)."""

class InvalidNodeError(ZeekControlError):
    """Indicates an attempt to lookup an invalid node name."""

class ConfigurationError(ZeekControlError):
    """Indicates a problem with the ZeekControl configuration."""

class CommandSyntaxError(ZeekControlError):
    """Indicates a syntax error in a ZeekControl command."""
