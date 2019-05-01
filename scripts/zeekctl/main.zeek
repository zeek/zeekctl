# Load the script to support the "scripts" command.
@load misc/loaded-scripts

# All cluster nodes are inherently controllable with ZeekControl.
@load frameworks/control/controllee

redef Control::controllee_listen = F;

## Reconfigure the reporter framework to stop printing to STDERR
## because STDERR is redirected and not normally visible when through
## ZeekControl.  The logs will still be available through the normal
## reporter stream in the logging framework.
redef Reporter::warnings_to_stderr = F;
redef Reporter::errors_to_stderr = F;
