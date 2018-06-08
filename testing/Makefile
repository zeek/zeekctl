
DIAG=diag.log
BTEST=../../btest/btest

all: cleanup buildbro btest-verbose

# Showing all tests.
btest-verbose:
	@$(BTEST) -j -f $(DIAG)

brief: cleanup buildbro btest-brief

# Brief output showing only failed tests.
btest-brief:
	@$(BTEST) -j -b -f $(DIAG)

# Rerun only the failed tests.
rerun:
	@$(BTEST) -r -j -f $(DIAG)

buildbro:
	@./Scripts/build-bro

cleanup:
	@rm -f $(DIAG)
	@rm -f .btest.failed.dat
	@rm -rf .tmp

# Remove the bro testing install dirs and tar file.
cleanall: cleanup
	@./Scripts/build-bro --clean

.PHONY: all btest-verbose btest-brief brief rerun buildbro cleanup cleanall
