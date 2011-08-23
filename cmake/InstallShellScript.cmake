# Schedules a file to be installed by the 'install' target, but first
# transformed by configure_file(... @ONLY) as well as by changing the
# shell script's hashbang (#!) line to use the absolute path to the
# interpreter in the path of the user running ./configure (or CMake equiv.).
#
# Hashbangs are not transformed when in binary packaging mode because,
# if NMI systems are to be used in creating binary packages, that could
# result in picking up a python interpreter in a non-standard location for
# a given distro. (NMI tends to install non-essential prerequisite packages
# in atypical locations).
#
# _dstdir: absolute path to the directory in which to install the transformed
#     source file
# _srcfile: path relevant to CMAKE_CURRENT_SOURCE_DIR pointing to the shell
#     script to install
# [_dstfilename]: an optional argument for how to (re)name the file as
#     it's installed inside _dstdir

macro(InstallShellScript _dstdir _srcfile)
    if (NOT "${ARGN}" STREQUAL "")
        set(_dstfilename ${ARGN})
    else ()
        get_filename_component(_dstfilename ${_srcfile} NAME)
    endif ()

    set(orig_file ${CMAKE_CURRENT_SOURCE_DIR}/${_srcfile})
    set(configed_file ${CMAKE_CURRENT_BINARY_DIR}/${_srcfile})
    set(dehashbanged_file ${CMAKE_CURRENT_BINARY_DIR}/${_srcfile}.dehashbanged)

    configure_file(${orig_file} ${configed_file} @ONLY)

    file(READ ${configed_file} _srclines)
    file(WRITE ${dehashbanged_file} "")

    if (NOT BINARY_PACKAGING_MODE)
        set(_regex "^#![ ]*/usr/bin/env[ ]+([^\n ]*)")
        string(REGEX MATCH ${_regex} _match ${_srclines})
        if (_match)
            set(_shell ${CMAKE_MATCH_1})
            find_program(${_shell}_interp ${_shell})
            if (NOT ${_shell}_interp)
                message(FATAL_ERROR
                       "Absolute path to interpreter '${_shell}' not found, "
                       "failed to configure shell script: ${orig_file}")
            endif ()

            string(REGEX REPLACE ${_regex} "#!${${_shell}_interp}"
                   _srclines "${_srclines}")
        endif ()
    endif ()

    file(WRITE ${dehashbanged_file} "${_srclines}")

    install(PROGRAMS ${dehashbanged_file}
            DESTINATION ${_dstdir}
            RENAME ${_dstfilename})
endmacro(InstallShellScript)
