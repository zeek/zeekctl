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

    file(READ ${CMAKE_CURRENT_SOURCE_DIR}/${_srcfile} _srclines)
    file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/${_srcfile} "")

    if (NOT BINARY_PACKAGING_MODE)
        set(_regex "^#![ ]*/usr/bin/env[ ]+([^\n ]*)")
        string(REGEX MATCH ${_regex} _match ${_srclines})
        if (_match)
            set(_shell ${CMAKE_MATCH_1})
            find_program(${_shell}_interp ${_shell})
            if (NOT ${_shell}_interp)
                message(FATAL_ERROR
                       "Absolute path to interpreter '${_shell}' not found, "
                       "failed to configure shell script: "
                       " ${CMAKE_CURRENT_SOURCE_DIR}/${_srcfile}")
            endif ()

            string(REGEX REPLACE ${_regex} "#!${${_shell}_interp}"
                   _srclines "${_srclines}")
        endif ()
    endif ()

    string(CONFIGURE "${_srclines}" _cfgdlines @ONLY)
    file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/${_srcfile} "${_cfgdlines}")

    install(PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/${_srcfile}
            DESTINATION ${_dstdir}
            RENAME ${_dstfilename})
endmacro(InstallShellScript)
