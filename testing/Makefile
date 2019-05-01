
DIAG=diag.log
BTEST=../../btest/btest

all: cleanup buildzeek btest-verbose

# Showing all tests.
btest-verbose:
	@$(BTEST) -j -f $(DIAG)

brief: cleanup buildzeek btest-brief

# Brief output showing only failed tests.
btest-brief:
	@$(BTEST) -j -b -f $(DIAG)

# Rerun only the failed tests.
rerun:
	@$(BTEST) -r -j -f $(DIAG)

buildzeek:
	@./Scripts/build-zeek

cleanup:
	@rm -f $(DIAG)
	@rm -f .btest.failed.dat
	@rm -rf .tmp

# Remove the zeek testing install dirs and tar file.
cleanall: cleanup
	@./Scripts/build-zeek --clean

.PHONY: all btest-verbose btest-brief brief rerun buildzeek cleanup cleanall
