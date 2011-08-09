##! Local site policy loaded only by the manager if BroControl is running Bro
##! in a clustered configuration (see node.cfg). 

# If you are running a cluster (as opposed to standalone mode) you should 
# define your Notice::policy here so that notice processing occurs on the
# manager.
redef Notice::policy += {

};
