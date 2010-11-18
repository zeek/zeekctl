# - Try to find capstats program
#
# Usage of this module as follows:
#
#  find_package(Capstats)
#
# Variables defined by this module:
#
#  CAPSTATS_FOUND             capstats binary found
#  Capstats_EXE               path to the capstats executable binary

find_program(CAPSTATS_EXE capstats)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(Capstats DEFAULT_MSG CAPSTATS_EXE)
