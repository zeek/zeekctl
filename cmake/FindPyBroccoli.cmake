# - Determine if the Broccoli Python bindings are available
#
# Usage of this module as follows:
#
#  find_package(PythonInterp REQUIRED)
#  find_package(PyBroccoli)
#
# Variables defined by this module:
#
#  PYBROCCOLI_FOUND             Python successfully imports broccoli bindings

execute_process(COMMAND ${PYTHON_EXECUTABLE} -c "import broccoli"
                RESULT_VARIABLE PYBROCCOLI_IMPORT_RESULT)

if (PYBROCCOLI_IMPORT_RESULT)
    # python returned non-zero exit status
    set(PYBROCCOLI_FOUND false)
else ()
    set(PYBROCCOLI_FOUND true)
endif ()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(PyBroccoli DEFAULT_MSG PYBROCCOLI_FOUND)
