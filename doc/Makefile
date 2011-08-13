#
#
# Builds the top-level README from its parts.

all: generate-docs
	cat README.main | awk -f include.awk >../README
	if which rst2html.py >/dev/null 2>&1; then \
		rst2html.py ../README >../README.html; \
	else \
		rst2html ../README >../README.html; \
	fi

generate-docs:
	@python ../BroControl/options.py >README.options
	@python ../BroControl/doc.py >README.plugins
	@python ../bin/broctl.in --print-doc >README.cmds
