# - Try to find Bro auxilliary tools programs
#
# Usage of this module as follows:
#
#  find_package(BroAuxTools)
#
# Variables defined by this module:
#
#  BroAuxTools_FOUND             Bro auxilliary tools found
#  HF_EXE                        path to the 'hf' binary
#  CF_EXE                        path to the 'cf' binary

find_program(HF_EXE hf)
find_program(CF_EXE cf)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(BroAuxTools DEFAULT_MSG HF_EXE CF_EXE)
