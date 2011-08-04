# Just terminate Bro after it parsed its configuration.

event bro_init() &priority = -10
{
	terminate();
}



