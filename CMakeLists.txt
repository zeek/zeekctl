cmake_minimum_required(VERSION 3.5 FATAL_ERROR)
project(ZeekControl C CXX)

include(GNUInstallDirs)
include(cmake/CommonCMakeConfig.cmake)

file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" VERSION LIMIT_COUNT 1)

set(PREFIX "${CMAKE_INSTALL_PREFIX}")
set(LIBDIR "${CMAKE_INSTALL_FULL_LIBDIR}")
set(ZEEKSCRIPTDIR "${ZEEK_SCRIPT_INSTALL_PATH}")
set(ETC "${ZEEK_ETC_INSTALL_DIR}")

########################################################################
## Dependency Configuration

include(FindRequiredPackage)

if (EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/auxil/pysubnettree/CMakeLists.txt)
    add_subdirectory(auxil/pysubnettree)
    set(SUBNETTREE_FOUND true)
    set(SUBNETTREE_PYTHON_MODULE "build from source auxil/pysubnettree")
endif ()

if (EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/auxil/capstats/CMakeLists.txt)
    add_subdirectory(auxil/capstats)
else ()
    find_package(Capstats)
endif ()

if (EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/auxil/trace-summary/CMakeLists.txt)
    add_subdirectory(auxil/trace-summary)
else ()
    find_package(TraceSummary)
endif ()

find_package(Zeek)
list(APPEND Python_ADDITIONAL_VERSIONS 3)
FindRequiredPackage(PythonInterp)
FindRequiredPackage(SubnetTree)
find_package(PCAP)

find_program(SENDMAIL sendmail PATHS /usr/sbin)
if (NOT SENDMAIL)
    message(WARNING "A sendmail program was not found, ZeekControl will be "
                    "unable to send mail.")
    # Set a path now so that the user won't need to edit zeekctl.cfg after
    # installing sendmail.
    set(SENDMAIL /usr/sbin/sendmail)
endif ()

if (MISSING_PREREQS)
    foreach (prereq ${MISSING_PREREQ_DESCS})
        message(SEND_ERROR ${prereq})
    endforeach ()
    message(FATAL_ERROR "Configuration aborted due to missing prerequisites")
endif ()

set(ZEEKCTL_PYTHON_MIN 3.5.0)

if ( PYTHON_VERSION_STRING VERSION_LESS ${ZEEKCTL_PYTHON_MIN} )
    message(FATAL_ERROR "Python ${ZEEKCTL_PYTHON_MIN} or greater is required.")
endif ()

if (NOT CMAKE_CROSSCOMPILING)
    execute_process(COMMAND "${PYTHON_EXECUTABLE}" -c "import sqlite3"
                    RESULT_VARIABLE PYSQLITE3_IMPORT_RESULT)

    if ( NOT PYSQLITE3_IMPORT_RESULT EQUAL 0 )
        message(FATAL_ERROR "The sqlite3 python module is required to use "
                "ZeekControl, but was not found.  Configuration aborted.")
    endif ()
endif ()

if (NOT ZEEK_ROOT_DIR)
    message(WARNING "A Zeek installation was not found, your ZeekControl "
                    " installation may not work.  Please review the install "
                    " summary before proceeding or force a Zeek root directory "
                    " with the --with-zeek configure option. ")
elseif (NOT "${ZEEK_ROOT_DIR}" STREQUAL "${CMAKE_INSTALL_PREFIX}")
    message(WARNING "ZeekControl installation directory ${CMAKE_INSTALL_PREFIX} "
                    "does not match Zeek installation directory ${ZEEK_ROOT_DIR}")
endif ()

########################################################################
## Python module installation setup

# We inherit a PY_MOD_INSTALL_DIR module installation path from Zeek
# when bundled with it. If that variable is not available, figure it
# out locally. Compare to similar logic in Broker's Python bindings.

if ( NOT PY_MOD_INSTALL_DIR )
  # Figure out Python module install directory.
  if (ZEEKCTL_PYTHON_PREFIX)
    set(pyver ${PYTHON_VERSION_MAJOR}.${PYTHON_VERSION_MINOR})
    set(PY_MOD_INSTALL_DIR
        ${ZEEKCTL_PYTHON_PREFIX}/lib/python${pyver}/site-packages)
  elseif (ZEEKCTL_PYTHON_HOME)
    set(PY_MOD_INSTALL_DIR ${ZEEKCTL_PYTHON_HOME}/lib/python)
  else ()
    execute_process(COMMAND ${PYTHON_EXECUTABLE} -c
      "from distutils.sysconfig import get_python_lib; print(get_python_lib())"
      OUTPUT_VARIABLE python_site_packages
      OUTPUT_STRIP_TRAILING_WHITESPACE)
    set(PY_MOD_INSTALL_DIR ${python_site_packages})
  endif ()
endif ()

########################################################################
## Install

include(InstallPackageConfigFile)
include(InstallSymlink)
include(InstallShellScript)

set(policydir ${ZEEK_SCRIPT_INSTALL_PATH})

# If a script may need to be configured by CMake and also have its hashbang
# transformed to use an absolute path to an interpreter, use the
# InstallShellScript macro.
InstallShellScript(bin bin/zeekctl.in zeekctl)
#InstallShellScript(bin bin/zeekctld.in zeekctld)
InstallShellScript(share/zeekctl/scripts bin/archive-log)
InstallShellScript(share/zeekctl/scripts bin/check-config)
InstallShellScript(share/zeekctl/scripts bin/crash-diag)
InstallShellScript(share/zeekctl/scripts bin/delete-log)
InstallShellScript(share/zeekctl/scripts bin/expire-crash)
InstallShellScript(share/zeekctl/scripts bin/expire-logs)
InstallShellScript(share/zeekctl/scripts bin/make-archive-name)
InstallShellScript(share/zeekctl/scripts bin/post-terminate)
InstallShellScript(share/zeekctl/scripts bin/run-zeek)
InstallShellScript(share/zeekctl/scripts bin/run-zeek-on-trace)
InstallShellScript(share/zeekctl/scripts bin/send-mail)
InstallShellScript(share/zeekctl/scripts bin/stats-to-csv)
InstallShellScript(share/zeekctl/scripts/helpers bin/helpers/check-pid)
InstallShellScript(share/zeekctl/scripts/helpers bin/helpers/df)
InstallShellScript(share/zeekctl/scripts/helpers bin/helpers/first-line)
InstallShellScript(share/zeekctl/scripts/helpers bin/helpers/start)
InstallShellScript(share/zeekctl/scripts/helpers bin/helpers/stop)
InstallShellScript(share/zeekctl/scripts/helpers bin/helpers/top)
InstallShellScript(share/zeekctl/scripts/postprocessors bin/postprocessors/summarize-connections)

install(DIRECTORY ZeekControl
        DESTINATION ${PY_MOD_INSTALL_DIR}/zeekctl
        PATTERN "options.py" EXCLUDE
        PATTERN "ssh_runner.py" EXCLUDE
        PATTERN "version.py" EXCLUDE
        PATTERN "zeekctld.py" EXCLUDE
        PATTERN "ser.py" EXCLUDE
        PATTERN "test_cli.py" EXCLUDE
        PATTERN "web.py" EXCLUDE
        PATTERN "plugins*" EXCLUDE)
configure_file(ZeekControl/options.py
               ${CMAKE_CURRENT_BINARY_DIR}/ZeekControl/options.py @ONLY)
configure_file(ZeekControl/ssh_runner.py
               ${CMAKE_CURRENT_BINARY_DIR}/ZeekControl/ssh_runner.py @ONLY)
configure_file(ZeekControl/version.py
               ${CMAKE_CURRENT_BINARY_DIR}/ZeekControl/version.py @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/ZeekControl/options.py
        DESTINATION ${PY_MOD_INSTALL_DIR}/zeekctl/ZeekControl)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/ZeekControl/ssh_runner.py
        DESTINATION ${PY_MOD_INSTALL_DIR}/zeekctl/ZeekControl)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/ZeekControl/version.py
        DESTINATION ${PY_MOD_INSTALL_DIR}/zeekctl/ZeekControl)
install(DIRECTORY ZeekControl/plugins
        DESTINATION ${PY_MOD_INSTALL_DIR}/zeekctl)

# Special cases where execute permission isn't applicable.
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/bin/helpers/to-bytes.awk
        DESTINATION share/zeekctl/scripts/helpers)
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/bin/set-zeek-path
        DESTINATION share/zeekctl/scripts)

if ( NOT ZEEK_MAN_INSTALL_PATH )
    set(ZEEK_MAN_INSTALL_PATH ${CMAKE_INSTALL_PREFIX}/share/man)
endif ()

install(FILES man/zeekctl.8 DESTINATION ${ZEEK_MAN_INSTALL_PATH}/man8)

install(DIRECTORY scripts/
        DESTINATION ${ZEEK_SCRIPT_INSTALL_PATH}
        FILES_MATCHING
        PATTERN "*.zeek")

if ( ZEEK_LOCAL_STATE_DIR )
    set(VAR ${ZEEK_LOCAL_STATE_DIR})
else ()
    set(VAR ${PREFIX})
endif ()

if ( ZEEK_SPOOL_DIR )
    set(SPOOL ${ZEEK_SPOOL_DIR})
else ()
    set(SPOOL ${VAR}/spool)
endif ()

if ( ZEEK_LOG_DIR )
    set(LOGS ${ZEEK_LOG_DIR})
else ()
    set(LOGS ${VAR}/logs)
endif ()

if ( BINARY_PACKAGING_MODE AND NOT APPLE )
    # Packaging for Apple-based systems does not need special logic
    # because many probably find it more convenient for uninstalling
    # when everything resides under a common prefix (since there's no
    # native package management system)
    set(perms OWNER_READ OWNER_WRITE OWNER_EXECUTE
              GROUP_READ GROUP_WRITE GROUP_EXECUTE
              WORLD_READ WORLD_WRITE WORLD_EXECUTE)

    install(DIRECTORY DESTINATION ${SPOOL}
            DIRECTORY_PERMISSIONS ${perms})
    install(DIRECTORY DESTINATION ${SPOOL}/tmp
            DIRECTORY_PERMISSIONS ${perms})
    install(DIRECTORY DESTINATION ${SPOOL}/brokerstore
            DIRECTORY_PERMISSIONS ${perms})
    install(DIRECTORY DESTINATION ${LOGS}
            DIRECTORY_PERMISSIONS ${perms})
    set(EMPTY_WORLD_DIRS
        "${EMPTY_WORLD_DIRS} ${SPOOL} ${SPOOL}/tmp ${LOGS}"
        CACHE STRING "" FORCE)
else ()
    install(DIRECTORY DESTINATION ${SPOOL})
    install(DIRECTORY DESTINATION ${SPOOL}/tmp)
    install(DIRECTORY DESTINATION ${SPOOL}/brokerstore)
    install(DIRECTORY DESTINATION ${LOGS})
endif ()

file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/zeekctl-config.sh
     "# Automatically generated. Do not edit.\n")
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/zeekctl-config.sh DESTINATION ${SPOOL})
InstallSymlink(${SPOOL}/zeekctl-config.sh
               ${PREFIX}/share/zeekctl/scripts/zeekctl-config.sh)

# A couple of configuration options that are needed are placed in here.
configure_file(etc/zeekctl.cfg.in
               ${CMAKE_CURRENT_BINARY_DIR}/etc/zeekctl.cfg)

if ( NOT BINARY_PACKAGING_MODE )
  # If the user has a broctl.cfg file from a previous installation,
  # but no zeekctl.cfg, abort.

  set(_broctl_cfg_dst ${ETC}/broctl.cfg)
  set(_zeekctl_cfg_dst ${ETC}/zeekctl.cfg)

  install(CODE "
    if ( \"\$ENV{DESTDIR}\" STREQUAL \"\" )
      if ( EXISTS \"${_broctl_cfg_dst}\" AND NOT EXISTS \"${_zeekctl_cfg_dst}\" )
        message(FATAL_ERROR \"${_broctl_cfg_dst} exists, but ${_zeekctl_cfg_dst} does not; rename it\")
      endif ()
    endif ()
  ")
endif ()

InstallPackageConfigFile(
    ${CMAKE_CURRENT_BINARY_DIR}/etc/zeekctl.cfg
    ${ETC}
    zeekctl.cfg)
InstallPackageConfigFile(
    ${CMAKE_CURRENT_SOURCE_DIR}/etc/networks.cfg
    ${ETC}
    networks.cfg)
InstallPackageConfigFile(
    ${CMAKE_CURRENT_SOURCE_DIR}/etc/node.cfg
    ${ETC}
    node.cfg)

if ( NOT BINARY_PACKAGING_MODE )
  # Need to remove pre-existing broctl dir from previous installs.
  set(_broctl_lib_dst ${LIBDIR}/broctl)

  install(CODE "
    if ( \"\$ENV{DESTDIR}\" STREQUAL \"\" )
      if ( EXISTS \"${_broctl_lib_dst}\" AND NOT IS_SYMLINK \"${_broctl_lib_dst}\" AND IS_DIRECTORY \"${_broctl_lib_dst}\" )
        message(STATUS \"WARNING: removing old directory ${_broctl_lib_dst}\")
        execute_process(COMMAND \"${CMAKE_COMMAND}\" -E rm -rf \"${_broctl_lib_dst}\")
      endif ()
    endif ()
  ")
endif ()

InstallSymlink("${PY_MOD_INSTALL_DIR}/zeekctl" "${LIBDIR}/broctl")
install(DIRECTORY BroControl DESTINATION ${PY_MOD_INSTALL_DIR}/zeekctl)

########################################################################
## Packaging Setup

# CPack RPM Generator may not automatically detect this
set(CPACK_RPM_PACKAGE_REQUIRES "python >= ${ZEEKCTL_PYTHON_MIN}")

# If this CMake project is a sub-project of another, we will not
# configure the generic packaging because CPack will fail in the case
# that the parent project has already configured packaging
if ("${PROJECT_SOURCE_DIR}" STREQUAL "${CMAKE_SOURCE_DIR}")
    include(ConfigurePackaging)
    ConfigurePackaging(${VERSION})
endif ()

########################################################################
## Build Summary

if (SPOOL)
    set(spoolDir ${SPOOL})
else ()
    set(spoolDir ${CMAKE_INSTALL_PREFIX}/spool)
endif ()

if (LOGS)
    set(logDir ${LOGS})
else ()
    set(logDir ${CMAKE_INSTALL_PREFIX}/logs)
endif ()

message(
    "\n=================|  ZeekControl Install Summary  |==================="
    "\n"
    "\nInstall prefix:    ${CMAKE_INSTALL_PREFIX}"
    "\nZeek root:         ${ZEEK_ROOT_DIR}"
    "\nScripts Dir:       ${policydir}"
    "\nSpool Dir:         ${spoolDir}"
    "\nLog Dir:           ${logDir}"
    "\nConfig File Dir:   ${ZEEK_ETC_INSTALL_DIR}"
    "\nPython Module Dir: ${PY_MOD_INSTALL_DIR}"
    "\n"
    "\n================================================================\n"
)

include(UserChangedWarning)
