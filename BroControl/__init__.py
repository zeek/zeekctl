from __future__ import print_function
import sys

msg="""
Warning: ZeekControl plugin uses legacy BroControl API. Use
'import ZeekControl.plugin' instead of 'import BroControl.plugin'
"""
print(msg, file=sys.stderr)
