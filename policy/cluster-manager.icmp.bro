redef FilterDuplicates::filters += {
    [ICMPAddressScan] = FilterDuplicates::match_src_num
};
	
