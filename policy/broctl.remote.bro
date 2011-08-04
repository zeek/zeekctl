@load broctl

# Configure Time Machine.
event bro_init()
	{
	if ( BroCtl::tm_host != 0.0.0.0 )
		Remote::destinations["time-machine"] = [$host=BroCtl::tm_host, $p=BroCtl::tm_port, $connect=T, $retry=1min];
	}

