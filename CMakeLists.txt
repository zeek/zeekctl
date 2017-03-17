project(BroControl C CXX)
# Python is checked as a dependency below
cmake_minimum_required(VERSION 2.6.3 FATAL_ERROR)
include(cmake/CommonCMakeConfig.cmake)

file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" VERSION LIMIT_COUNT 1)

set(PREFIX "${CMAKE_INSTALL_PREFIX}")
set(BROSCRIPTDIR "${BRO_SCRIPT_INSTALL_PATH}")
set(ETC "${BRO_ETC_INSTALL_DIR}")

########################################################################
## Dependency Configuration

include(FindRequiredPackage)

if (EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/aux/pysubnettree/CMakeLists.txt)
    add_subdirectory(aux/pysubnettree)
    set(SUBNETTREE_FOUND true)
    set(SUBNETTREE_PYTHON_MODULE "build from source aux/pysubnettree")
endif ()

if (EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/aux/capstats/CMakeLists.txt)
    add_subdirectory(aux/capstats)
else ()
    find_package(Capstats)
endif ()

if (EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/aux/trace-summary/CMakeLists.txt)
    add_subdirectory(aux/trace-summary)
else ()
    find_package(TraceSummary)
endif ()

find_package(Bro)
FindRequiredPackage(PythonInterp)
FindRequiredPackage(SubnetTree)
find_package(PCAP)

if (HAVE_PF_RING)
    set(PF_RING_CLUSTER_ID 21)
else ()
    set(PF_RING_CLUSTER_ID 0)
endif ()

find_program(SENDMAIL sendmail PATHS /usr/sbin)
if (NOT SENDMAIL)
    message(WARNING "A sendmail program was not found, BroControl will be "
                    "unable to send mail.  This can be fixed even after "
                    "installing by editing "
                    "${BRO_ETC_INSTALL_DIR}/broctl.cfg")
endif ()

if (MISSING_PREREQS)
    foreach (prereq ${MISSING_PREREQ_DESCS})
        message(SEND_ERROR ${prereq})
    endforeach ()
    message(FATAL_ERROR "Configuration aborted due to missing prerequisites")
endif ()

execute_process(COMMAND "${PYTHON_EXECUTABLE}" -c "import sqlite3"
                RESULT_VARIABLE PYSQLITE3_IMPORT_RESULT)

if ( NOT PYSQLITE3_IMPORT_RESULT EQUAL 0 )
    message(FATAL_ERROR "The sqlite3 python module is required to use "
            "BroControl, but was not found.  Configuration aborted.")
endif ()

if (NOT BRO_ROOT_DIR)
    message(WARNING "A Bro installation was not found, your BroControl "
                    " installation may not work.  Please review the install "
                    " summary before proceeding or force a Bro root directory "
                    " with the --with-bro configure option. ")
elseif (NOT "${BRO_ROOT_DIR}" STREQUAL "${CMAKE_INSTALL_PREFIX}")
    message(WARNING "Broctl installation directory ${CMAKE_INSTALL_PREFIX} "
                    "does not match Bro installation directory ${BRO_ROOT_DIR}")
endif ()

########################################################################
## Install

include(InstallPackageConfigFile)
include(InstallSymlink)
include(InstallShellScript)

set(policydir ${BRO_SCRIPT_INSTALL_PATH})

# If a script may need to be configured by CMake and also have its hashbang
# transformed to use an absolute path to an interpreter, use the
# InstallShellScript macro.
InstallShellScript(bin bin/broctl.in broctl)
#InstallShellScript(bin bin/broctld.in broctld)
InstallShellScript(share/broctl/scripts bin/archive-log)
InstallShellScript(share/broctl/scripts bin/check-config)
InstallShellScript(share/broctl/scripts bin/crash-diag)
InstallShellScript(share/broctl/scripts bin/delete-log)
InstallShellScript(share/broctl/scripts bin/expire-crash)
InstallShellScript(share/broctl/scripts bin/expire-logs)
InstallShellScript(share/broctl/scripts bin/make-archive-name)
InstallShellScript(share/broctl/scripts bin/post-terminate)
InstallShellScript(share/broctl/scripts bin/run-bro)
InstallShellScript(share/broctl/scripts bin/run-bro-on-trace)
InstallShellScript(share/broctl/scripts bin/send-mail)
InstallShellScript(share/broctl/scripts bin/stats-to-csv)
InstallShellScript(share/broctl/scripts bin/update)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/check-pid)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/df)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/first-line)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/get-childs)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/start)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/stop)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/top)
InstallShellScript(share/broctl/scripts/postprocessors bin/postprocessors/summarize-connections)

install(DIRECTORY BroControl
        DESTINATION lib/broctl
        PATTERN "options.py" EXCLUDE
        PATTERN "ssh_runner.py" EXCLUDE
        PATTERN "version.py" EXCLUDE
        PATTERN "broctld.py" EXCLUDE
        PATTERN "ser.py" EXCLUDE
        PATTERN "test_cli.py" EXCLUDE
        PATTERN "web.py" EXCLUDE
        PATTERN "plugins*" EXCLUDE)
configure_file(BroControl/options.py
               ${CMAKE_CURRENT_BINARY_DIR}/BroControl/options.py @ONLY)
configure_file(BroControl/ssh_runner.py
               ${CMAKE_CURRENT_BINARY_DIR}/BroControl/ssh_runner.py @ONLY)
configure_file(BroControl/version.py
               ${CMAKE_CURRENT_BINARY_DIR}/BroControl/version.py @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/BroControl/options.py
        DESTINATION lib/broctl/BroControl)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/BroControl/ssh_runner.py
        DESTINATION lib/broctl/BroControl)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/BroControl/version.py
        DESTINATION lib/broctl/BroControl)
install(DIRECTORY BroControl/plugins
        DESTINATION lib/broctl)

# Special cases where execute permission isn't applicable.
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/bin/helpers/to-bytes.awk
        DESTINATION share/broctl/scripts/helpers)
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/bin/set-bro-path
        DESTINATION share/broctl/scripts)

if ( NOT BRO_MAN_INSTALL_PATH )
    set(BRO_MAN_INSTALL_PATH ${CMAKE_INSTALL_PREFIX}/share/man)
endif ()

install(FILES man/broctl.8 DESTINATION ${BRO_MAN_INSTALL_PATH}/man8)

install(DIRECTORY scripts/
        DESTINATION ${BRO_SCRIPT_INSTALL_PATH}
        FILES_MATCHING
        PATTERN "*.bro")

if ( BRO_LOCAL_STATE_DIR )
    set(VAR ${BRO_LOCAL_STATE_DIR})
else ()
    set(VAR ${PREFIX})
endif ()

if ( BRO_SPOOL_DIR )
    set(SPOOL ${BRO_SPOOL_DIR})
else ()
    set(SPOOL ${VAR}/spool)
endif ()

if ( BRO_LOG_DIR )
    set(LOGS ${BRO_LOG_DIR})
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
    install(DIRECTORY DESTINATION ${LOGS}
            DIRECTORY_PERMISSIONS ${perms})
    set(EMPTY_WORLD_DIRS
        "${EMPTY_WORLD_DIRS} ${SPOOL} ${SPOOL}/tmp ${LOGS}"
        CACHE STRING "" FORCE)
else ()
    install(DIRECTORY DESTINATION ${SPOOL})
    install(DIRECTORY DESTINATION ${SPOOL}/tmp)
    install(DIRECTORY DESTINATION ${LOGS})
endif ()

file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/broctl-config.sh
     "# Automatically generated. Do not edit.\n")
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/broctl-config.sh DESTINATION ${SPOOL})
InstallSymlink(${SPOOL}/broctl-config.sh
               ${PREFIX}/share/broctl/scripts/broctl-config.sh)

# A couple of configuration options that are needed are placed in here.
configure_file(etc/broctl.cfg.in
               ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg)

InstallPackageConfigFile(
    ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg
    ${ETC}
    broctl.cfg)
InstallPackageConfigFile(
    ${CMAKE_CURRENT_SOURCE_DIR}/etc/networks.cfg
    ${ETC}
    networks.cfg)
InstallPackageConfigFile(
    ${CMAKE_CURRENT_SOURCE_DIR}/etc/node.cfg
    ${ETC}
    node.cfg)

########################################################################
## Packaging Setup

# CPack RPM Generator may not automatically detect this
set(CPACK_RPM_PACKAGE_REQUIRES "python >= 2.6.0")

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
    "\n=================|  Broctl Install Summary  |==================="
    "\n"
    "\nInstall prefix:    ${CMAKE_INSTALL_PREFIX}"
    "\nBro root:          ${BRO_ROOT_DIR}"
    "\nScripts Dir:       ${policydir}"
    "\nSpool Dir:         ${spoolDir}"
    "\nLog Dir:           ${logDir}"
    "\nConfig File Dir:   ${BRO_ETC_INSTALL_DIR}"
    "\n"
    "\n================================================================\n"
)

include(UserChangedWarning)
