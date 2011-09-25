# Converts strings such as 12K, 42M, etc. into bytes. 
# If def_factor is set, it's applied to values without any unit.

BEGIN {
    if ( def_factor == 0 )
        def_factor = 1;
    }
      
{
    for ( i = 1; i <= NF; i++) {
	    if ( match($i, "^(-?[0-9.]+)By?$") ){ $i = int(substr($i, RSTART, RLENGTH-1)); }
 	    else if ( match($i, "^(-?[0-9.]+)[kK]i?$") ){ $i = int(substr($i, RSTART, RLENGTH-1) * 1024); }
	    else if ( match($i, "^(-?[0-9.]+)[mM]i?$") ){ $i = int(substr($i, RSTART, RLENGTH-1) * 1024 * 1024); }
	    else if ( match($i, "^(-?[0-9.]+)[gG]i?$") ){ $i = int(substr($i, RSTART, RLENGTH-1) * 1024 * 1024 * 1024); }
	    else if ( match($i, "^(-?[0-9.]+)[tT]e?$") ){ $i = int(substr($i, RSTART, RLENGTH-1) * 1024 * 1024 * 1024 * 1024); }
	    else if ( match($i, "^(-?[0-9.]+)$") )   { $i = int(substr($i, RSTART, RLENGTH) * def_factor); }
	    printf("%s ", $i);
	}

    print ""; 
}
