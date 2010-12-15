# - Determine if the SubnetTree Python module is available
#
# Usage of this module as follows:
#
#  find_package(PythonInterp REQUIRED)
#  find_package(SubnetTree)
#
# Variables defined by this module:
#
#  SUBNETTREE_FOUND             Python successfully imports SubnetTree module

if (NOT SUBNETTREE_FOUND)
    execute_process(COMMAND "${PYTHON_EXECUTABLE}" -c "import SubnetTree"
                    RESULT_VARIABLE SUBNETTREE_IMPORT_RESULT)

    if (SUBNETTREE_IMPORT_RESULT)
        # python returned non-zero exit status
        set(SUBNETTREE_PYTHON_MODULE false)
    else ()
        set(SUBNETTREE_PYTHON_MODULE true)
    endif ()
endif ()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(SubnetTree DEFAULT_MSG
                                  SUBNETTREE_PYTHON_MODULE)
