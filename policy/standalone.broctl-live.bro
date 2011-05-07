#
# Only loaded when running live, not when just checking configuration.
#

@load print-filter

redef PrintFilter::terminate_bro = F;
redef PrintFilter::to_file = T; 

