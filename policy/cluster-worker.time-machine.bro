# We connect the TM to the manager which relays (and logs) commands so we
# do not propagate the worker's TM logs.

redef TimeMachine::logfile &disable_print_hook;
