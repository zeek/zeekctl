# BroControl exceptions.
#
# These are the exceptions that are expected to be raised under predictable
# circumstances (such as bad user input, or an invalid configuration).  When
# these are raised, a text message explaining the problem should be provided.
# Therefore, these should be caught to avoid seeing a stack trace (which
# provides no new information in these cases).  However, standard Python
# exceptions are not expected to occur, so if one is raised a stack trace
# can provide valuable information on the source of the problem.

class BroControlError(Exception):
    """This is the base class for BroControl exceptions."""

class LockError(BroControlError):
    """Indicates that BroControl was unable to obtain a lock."""

class RuntimeEnvironmentError(BroControlError):
    """Indicates an error in the runtime environment (e.g. running as wrong
    user, or some files/directories have wrong permissions or location)."""

class InvalidNodeError(BroControlError):
    """Indicates an attempt to lookup an invalid node name."""

class ConfigurationError(BroControlError):
    """Indicates a problem with the BroControl configuration."""

class CommandSyntaxError(BroControlError):
    """Indicates a syntax error in a BroControl command."""
