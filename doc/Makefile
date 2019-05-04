# Builds the top-level zeekctl.rst from its parts.
#
# Note: It's not great to build this here and commit to the repository
# (as opposed to in build/). However, otherwise it would get hard
# to put the final document online www.zeek.org.

all: generate-docs

generate-docs:
	@echo "Creating zeekctl.rst ..."
	@PYTHONPATH=.. ../bin/zeekctl.in --print-doc main.rst >zeekctl.rst
