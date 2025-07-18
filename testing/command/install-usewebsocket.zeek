# Test that the install command recognizes the UseWebSocket, WebSocketHost and
# WebSocketPort settings.
#
# @TEST-EXEC: bash %INPUT
#
# @TEST-EXEC: zeek --parse-only cluster-layout-base
# @TEST-EXEC: zeek --parse-only cluster-layout-use-websocket
# @TEST-EXEC: zeek --parse-only cluster-layout-use-websocket-custom
#
# @TEST-EXEC: TEST_DIFF_CANONIFIER=$SCRIPTS/diff-cluster-layout btest-diff cluster-layout-base
# @TEST-EXEC: TEST_DIFF_CANONIFIER=$SCRIPTS/diff-cluster-layout btest-diff cluster-layout-use-websocket
# @TEST-EXEC: TEST_DIFF_CANONIFIER=$SCRIPTS/diff-cluster-layout btest-diff cluster-layout-use-websocket-custom

. zeekctl-test-setup

clusterlayout=$ZEEKCTL_INSTALL_PREFIX/spool/installed-scripts-do-not-touch/auto/cluster-layout.zeek


installfile etc/node.cfg__cluster
zeekctl install
cp $clusterlayout cluster-layout-base

# Change the configuration to enable the WebSocket for Zeekctl interaction.
echo "usewebsocket=1" >> $ZEEKCTL_INSTALL_PREFIX/etc/zeekctl.cfg
zeekctl install
cp $clusterlayout cluster-layout-use-websocket

# Fiddle with the listening configuration.
echo "WebSocketHost=[::1]" >> $ZEEKCTL_INSTALL_PREFIX/etc/zeekctl.cfg
echo "WebSocketPort=1234" >> $ZEEKCTL_INSTALL_PREFIX/etc/zeekctl.cfg
zeekctl install
cp $clusterlayout cluster-layout-use-websocket-custom
