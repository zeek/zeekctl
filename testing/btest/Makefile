
DIAG=diag.log
BTEST=../../../btest/btest

all: cleanup buildbro btest-verbose

# Showing all tests.
btest-verbose:
	@$(BTEST) -j 4 -f $(DIAG)

buildbro:
	@../scripts/build-bro

cleanup:
	@rm -f $(DIAG)
	@../scripts/build-bro cleanup

.PHONY: all btest-verbose buildbro cleanup
