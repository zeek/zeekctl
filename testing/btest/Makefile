
DIAG=diag.log
BTEST=../../../btest/btest

all: btest-verbose

# Showing all tests.
btest-verbose: buildbro
	@$(BTEST) -j 4 -f $(DIAG)

buildbro: cleanup
	@../scripts/build-bro

cleanup:
	@rm -f $(DIAG)
	@../scripts/build-bro cleanup

.PHONY: all btest-verbose buildbro cleanup
