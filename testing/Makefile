
DIAG=diag.log
BTEST=../../btest/btest
BROSRC=..

all: btest-verbose

# Showing all tests.
btest-verbose: buildbro
	@$(BTEST) -j -f $(DIAG)

# Showing all tests, but not building Bro.
btest-quick:
	@$(BTEST) -j -f $(DIAG)

brief: btest-brief
quick: btest-quick

# Brief output showing only failed tests.
btest-brief: buildbro
	@$(BTEST) -j -b -f $(DIAG)

buildbro: cleanup
	@./Scripts/build-bro

cleanup:
	@rm -f $(DIAG)
	@./Scripts/build-bro cleanup

.PHONY: all btest-verbose btest-brief brief buildbro cleanup
