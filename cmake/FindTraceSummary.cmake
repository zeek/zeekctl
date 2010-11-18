# - Try to find the trace-summary Python program
#
# Usage of this module as follows:
#
#  find_package(TraceSummary)
#
# Variables defined by this module:
#
#  TRACESUMMARY_FOUND             capstats binary found
#  TraceSummary_EXE               path to the capstats executable binary

find_program(TRACE_SUMMARY_EXE trace-summary)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(TraceSummary DEFAULT_MSG TRACE_SUMMARY_EXE)
