# @TEST-DOC: Redefining a ZeroMQ option in local.zeek should work.
#
# @TEST-SERIALIZE: listen
#
# @TEST-EXEC: bash %INPUT
# @TEST-EXEC: btest-diff out

. zeekctl-test-setup

# Test with a standalone config.
cat > $ZEEKCTL_INSTALL_PREFIX/etc/node.cfg << EOF
[zeek]
type=standalone
host=localhost
EOF

zeekctl install

# Verify that setting the onloop_queue_hwm option works.
echo "redef Cluster::Backend::ZeroMQ::onloop_queue_hwm = 123456;" >> $ZEEKCTL_INSTALL_PREFIX/spool/installed-scripts-do-not-touch/site/local.zeek
zeekctl check >> out

# Start the cluster and use print to get the value that's used.
zeekctl start
zeekctl print Cluster::Backend::ZeroMQ::onloop_queue_hwm >> out
zeekctl stop
