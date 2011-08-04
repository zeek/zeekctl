redef FilterDuplicates::filters += {
    [ServerFound] = FilterDuplicates::match_src_port
};

