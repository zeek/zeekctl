
from __future__ import print_function
import sys

msg="""
Warning: ZeekControl plugin uses legacy BroControl API. Use
'import ZeekControl.plugin' instead of 'import BroControl.plugin'
"""
print(msg, file=sys.stderr)

# These two happenbe made available to imports by the plugin registry. Forward
# them so that old plugins can keep using them without needing new imports.
import ZeekControl.cmdresult
import ZeekControl.node
cmdresult = ZeekControl.cmdresult
node = ZeekControl.node
