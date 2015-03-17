# Builds the top-level broctl.rst from its parts.
#
# Note: It's not great to build this here and commit to the repository
# (as opposed to in build/). However, otherwise it would get hard
# to put the final document online www.bro.org.

all: generate-docs

generate-docs:
	@echo "Creating broctl.rst ..."
	@PYTHONPATH=.. ../bin/broctl.in --print-doc main.rst >broctl.rst
