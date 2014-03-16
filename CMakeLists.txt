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

InstallShellScript(bin bin/broctl.in broctl)
InstallShellScript(share/broctl/scripts bin/archive-log)
InstallShellScript(share/broctl/scripts bin/cflow-stats)
InstallShellScript(share/broctl/scripts bin/check-config)
InstallShellScript(share/broctl/scripts bin/crash-diag)
InstallShellScript(share/broctl/scripts bin/create-link-for-log)
InstallShellScript(share/broctl/scripts bin/delete-log)
InstallShellScript(share/broctl/scripts bin/expire-logs)
InstallShellScript(share/broctl/scripts bin/get-prof-log)
InstallShellScript(share/broctl/scripts bin/local-interfaces)
InstallShellScript(share/broctl/scripts bin/make-archive-name)
InstallShellScript(share/broctl/scripts bin/post-terminate)
InstallShellScript(share/broctl/scripts bin/remove-link-for-log)
InstallShellScript(share/broctl/scripts bin/run-bro)
InstallShellScript(share/broctl/scripts bin/send-mail)
InstallShellScript(share/broctl/scripts bin/stats-to-csv)
InstallShellScript(share/broctl/scripts bin/update)
InstallShellScript(share/broctl/scripts bin/update-stats)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/cat-file)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/check-pid)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/df)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/exists)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/gdb-attach)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/get-childs)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/is-dir)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/rmdir)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/run-cmd)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/start)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/stop)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/to-bytes.awk)
InstallShellScript(share/broctl/scripts/helpers bin/helpers/top)
InstallShellScript(share/broctl/scripts/postprocessors bin/postprocessors/summarize-connections)

install(DIRECTORY BroControl
        DESTINATION lib/broctl
        PATTERN "options.py" EXCLUDE
        PATTERN "plugins*" EXCLUDE)
configure_file(BroControl/options.py
               ${CMAKE_CURRENT_BINARY_DIR}/BroControl/options.py @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/BroControl/options.py
        DESTINATION lib/broctl/BroControl)
install(DIRECTORY BroControl/plugins
        DESTINATION lib/broctl)
install(DIRECTORY bin/
        DESTINATION share/broctl/scripts
        FILES_MATCHING
        PATTERN "*" PERMISSIONS
                        OWNER_READ OWNER_WRITE OWNER_EXECUTE
                        GROUP_READ GROUP_EXECUTE
                        WORLD_READ WORLD_EXECUTE
        PATTERN "broctl.in" EXCLUDE)
install(DIRECTORY scripts/
        DESTINATION ${BRO_SCRIPT_INSTALL_PATH}
        FILES_MATCHING
        PATTERN "*.bro")

# These are needed for the default broctl.cfg file but they may be changed
# below for packaging reasons.
set(SPOOL ${PREFIX}/spool)
set(LOGS ${PREFIX}/logs)

# Check the install prefixes to determine if we're creating a package
# Packaging for Apple-based systems does not need special logic
# because many probably find it more convenient for uninstalling
# when everything resides under a common prefix (since there's no
# native package management system)
if (NOT APPLE AND (${CMAKE_INSTALL_PREFIX} STREQUAL /usr OR
                   ${CMAKE_INSTALL_PREFIX} STREQUAL /opt/bro))

    # If the install prefix of /usr was given, change the install location
    # of the config file to be /etc instead of /usr/etc and the location of
    # runtime files to be in the appropriate directories under /var.
    # The runtime directories will be world-writable, so the packaging
    # post install script will make sure to set the sticky bit to prevent
    # unprivileged users from removing/renaming files.
    if (${CMAKE_INSTALL_PREFIX} STREQUAL /usr)
        # Don't make any assumption for config file install dir.  The default
        # of /usr/etc/ is usually wrong, but it's always explicitly configurable
        # with --conf-files-dir.
        set(VAR /var)
        # TODO: Consult FHS to see if these are appropriate. Also,
        #       packaging should do something more to protect the
        #       runtime directories, perhaps require group permissions?
        set(SPOOL ${VAR}/spool/bro)
        set(LOGS ${VAR}/log/bro)
    else ()
        # FHS says config files go in /etc/opt/bro, but until there's
        # a compelling reason to do that, they'll be kept along with
        # everything else under the installation prefix
        set(VAR /var/opt/bro)
        set(SPOOL ${VAR}/spool)
        set(LOGS ${VAR}/logs)
    endif ()

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
    InstallSymlink(${SPOOL}/broctl-config.sh
                   ${PREFIX}/share/broctl/scripts/broctl-config.sh)
else ()
    install(DIRECTORY DESTINATION spool)
    install(DIRECTORY DESTINATION spool/tmp)
    install(DIRECTORY DESTINATION logs)
    InstallSymlink(${PREFIX}/spool/broctl-config.sh
                   ${PREFIX}/share/broctl/scripts/broctl-config.sh)
endif ()

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
