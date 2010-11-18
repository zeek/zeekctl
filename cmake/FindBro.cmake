# - Try to find Bro installation
#
# Usage of this module as follows:
#
#  find_package(Bro)
#
# Variables used by this module, they can change the default behaviour and need
# to be set before calling find_package:
#
#  BRO_ROOT_DIR              Set this variable to the root installation of
#                            Bro if the module has problems finding the
#                            proper installation path.
#
# Variables defined by this module:
#
#  BRO_FOUND                     Bro NIDS is installed
#  BRO_EXE                       path to the 'bro' binary

if (BRO_EXE AND BRO_ROOT_DIR)
    # this implies that we're building from the Bro source tree
    set(BRO_FOUND true)
    return()
endif ()

find_program(BRO_EXE bro
             HINTS ${BRO_ROOT_DIR}/bin /usr/local/bro/bin)

if (BRO_EXE)
    get_filename_component(BRO_ROOT_DIR ${BRO_EXE} PATH)
    get_filename_component(BRO_ROOT_DIR ${BRO_ROOT_DIR} PATH)
endif ()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(Bro DEFAULT_MSG BRO_EXE)

mark_as_advanced(BRO_ROOT_DIR)
