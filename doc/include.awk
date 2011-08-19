BEGIN {

    s = 0
    input[s] = "/dev/stdin";

    for ( ; s >= 0; s--) {

        while ( (getline < input[s]) > 0) {
            if ( $1 == ".." && $2 == "include::" )
                input[++s] = $3;
            else
                print;
        }
        close(input[s])
    }
}
