DIAG := diag.log
BTEST := ../../btest/btest

ZEEK_TAR := ../build/testing/zeek-test-install.tar

all: btest-verbose

# Showing all tests.
btest-verbose: $(ZEEK_TAR)
	@$(BTEST) -j -f $(DIAG)

brief: cleanup btest-brief

# Brief output showing only failed tests.
btest-brief: $(ZEEK_TAR)
	@$(BTEST) -j -b -f $(DIAG)

# Rerun only the failed tests.
rerun: $(ZEEK_TAR)
	@$(BTEST) -r -j -f $(DIAG)

$(ZEEK_TAR):
	@./Scripts/build-zeek

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
