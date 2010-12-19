# $Id: to-bytes.awk 6811 2009-07-06 20:41:10Z robin $

# Converts strings such as 12K, 42M, etc. into bytes.

{
    for ( i = 1; i <= NF; i++) {
	    if ( match($i, "^(-?[0-9.]+)B[y+]?$") ){ $i = substr($i, RSTART, RLENGTH-1); }
 	    else if ( match($i, "^(-?[0-9.]+)K[i+]?$") ){ $i = substr($i, RSTART, RLENGTH-1) * 1024; }
	    else if ( match($i, "^(-?[0-9.]+)M[i+]?$") ){ $i = substr($i, RSTART, RLENGTH-1) * 1024 * 1024; }
	    else if ( match($i, "^(-?[0-9.]+)G[i+]?$") ){ $i = substr($i, RSTART, RLENGTH-1) * 1024 * 1024 * 1024; }
	    else if ( match($i, "^(-?[0-9.]+)T[e+]?$") ){ $i = substr($i, RSTART, RLENGTH-1) * 1024 * 1024 * 1024 * 1024; }
	    printf("%s ", $i);
	}

    print ""; 
}
