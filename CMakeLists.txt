project(Broctl NONE)
# Python is checked as a dependency below

########################################################################
## CMake Configuration

cmake_minimum_required(VERSION 2.6 FATAL_ERROR)

# Prohibit in-source builds.
if ("${CMAKE_SOURCE_DIR}" STREQUAL "${CMAKE_BINARY_DIR}")
    message(FATAL_ERROR "In-source builds are not allowed. Please use "
                        "./configure to choose a build directory and "
                        "initialize the build configuration.")
endif ()

set(CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/cmake)

if ("${PROJECT_SOURCE_DIR}" STREQUAL "${CMAKE_SOURCE_DIR}")
    # uninstall target
    configure_file("${CMAKE_CURRENT_SOURCE_DIR}/cmake/cmake_uninstall.cmake.in"
                   "${CMAKE_CURRENT_BINARY_DIR}/cmake_uninstall.cmake"
                    @ONLY)

    add_custom_target(uninstall COMMAND
        ${CMAKE_COMMAND} -P ${CMAKE_CURRENT_BINARY_DIR}/cmake_uninstall.cmake)
endif ()

########################################################################
## Project/Build Configuration

file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" VERSION LIMIT_COUNT 1)

set(PREFIX ${CMAKE_INSTALL_PREFIX})

if (STANDALONE)
    set(STANDALONE "True")
    set(cfgType "Standalone")
else ()
    set(STANDALONE "False")
    set(cfgType "Cluster")
endif ()

########################################################################
## Dependency Configuration

include(MacDependencyPaths)
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
## Generate/Configure files

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/bin/broctl.in
               ${CMAKE_CURRENT_BINARY_DIR}/bin/broctl)

########################################################################
## Install

include(InstallPackageConfigFile)

set(policydir ${BRO_ROOT_DIR}/share/bro)

install(PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/bin/broctl
        DESTINATION bin)
install(DIRECTORY BroControl
        DESTINATION lib/broctl)
install(DIRECTORY bin/
        DESTINATION share/broctl/scripts
        FILES_MATCHING
        PATTERN "*" PERMISSIONS
                        OWNER_READ OWNER_WRITE OWNER_EXECUTE
                        GROUP_READ GROUP_EXECUTE
                        WORLD_READ WORLD_EXECUTE
        PATTERN "broctl.in" EXCLUDE
        PATTERN "run-cmd.in" EXCLUDE)
install(DIRECTORY policy/
        DESTINATION share/bro/broctl
        FILES_MATCHING
        PATTERN "*.bro"
        PATTERN "local" EXCLUDE)

set(ETC ${PREFIX}/etc)

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
        set(ETC /etc)
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
    install(DIRECTORY DESTINATION ${SPOOL}/policy
            DIRECTORY_PERMISSIONS ${perms})
    install(DIRECTORY DESTINATION ${LOGS}
            DIRECTORY_PERMISSIONS ${perms})
    set(EMPTY_WORLD_DIRS
        "${EMPTY_WORLD_DIRS} ${SPOOL} ${SPOOL}/tmp ${SPOOL}/policy ${LOGS}"
        CACHE STRING "" FORCE)
    install(CODE "
        execute_process(COMMAND \"${CMAKE_COMMAND}\" -E create_symlink
                      ${SPOOL}/broctl-config.sh
                      ${PREFIX}/share/broctl/scripts/broctl-config.sh)
    ")
    # configure broctl.cfg point SpoolDir/LogDir to right runtime directories
    configure_file(etc/broctl.cfg.package.in
                   ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg)
else ()
    install(DIRECTORY DESTINATION spool)
    install(DIRECTORY DESTINATION spool/tmp)
    install(DIRECTORY DESTINATION spool/policy)
    install(DIRECTORY DESTINATION logs)
    # symlink install has to be scripted at install time for CMake 2.6 compat
    install(CODE "
        execute_process(COMMAND \"${CMAKE_COMMAND}\" -E create_symlink
                      ${PREFIX}/spool/broctl-config.sh
                      ${PREFIX}/share/broctl/scripts/broctl-config.sh)
    ")
    if (STANDALONE)
        configure_file(etc/broctl.cfg.standalone.in
                       ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg)
    else ()
        configure_file(etc/broctl.cfg.cluster.in
                       ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg)
    endif ()
endif ()

InstallPackageConfigFile(
    ${CMAKE_CURRENT_SOURCE_DIR}/etc/analysis.dat
    ${ETC}
    analysis.dat)
InstallPackageConfigFile(
    ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg
    ${ETC}
    broctl.cfg)
InstallPackageConfigFile(
    ${CMAKE_CURRENT_SOURCE_DIR}/etc/networks.cfg.in
    ${ETC}
    networks.cfg)

if (STANDALONE)
    # The policy file template is configured into build dir just
    # to assist running bro from the build directory
    configure_file(policy/local/standalone.local.bro-template
                   ${CMAKE_CURRENT_BINARY_DIR}/policy/local/local.bro
                   COPY_ONLY)
    InstallPackageConfigFile(
        ${CMAKE_CURRENT_SOURCE_DIR}/policy/local/standalone.local.bro-template
        ${PREFIX}/share/bro/site
        local.bro)
    InstallPackageConfigFile(
        ${CMAKE_CURRENT_SOURCE_DIR}/etc/node.cfg.standalone.in
        ${ETC}
        node.cfg)
else ()
    # The policy file templates are configured into build dir just
    # to assist running bro from the build directory
    configure_file(policy/local/cluster.local.bro-template
                   ${CMAKE_CURRENT_BINARY_DIR}/policy/local/local.bro
                   COPY_ONLY)
    configure_file(policy/local/cluster.local-worker.bro-template
                   ${CMAKE_CURRENT_BINARY_DIR}/policy/local/local-worker.bro
                   COPY_ONLY)
    configure_file(policy/local/cluster.local-manager.bro-template
                   ${CMAKE_CURRENT_BINARY_DIR}/policy/local/local-manager.bro
                   COPY_ONLY)

    InstallPackageConfigFile(
        ${CMAKE_CURRENT_SOURCE_DIR}/policy/local/cluster.local.bro-template
        ${PREFIX}/share/bro/site
        local.bro)
    InstallPackageConfigFile(
        ${CMAKE_CURRENT_SOURCE_DIR}/policy/local/cluster.local-worker.bro-template
        ${PREFIX}/share/bro/site
        local-worker.bro)
    InstallPackageConfigFile(
        ${CMAKE_CURRENT_SOURCE_DIR}/policy/local/cluster.local-manager.bro-template
        ${PREFIX}/share/bro/site
        local-manager.bro)
    InstallPackageConfigFile(
        ${CMAKE_CURRENT_SOURCE_DIR}/etc/node.cfg.cluster.in
        ${ETC}
        node.cfg)
endif ()

########################################################################
## Packaging Setup

# CPack RPM Generator may not automatically detect this
set(CPACK_RPM_PACKAGE_REQUIRES "python >= 2.4.0")

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
    "\nConfiguration:     ${cfgType}"
    "\n"
    "\nInstall prefix:    ${CMAKE_INSTALL_PREFIX}"
    "\nBro root:          ${BRO_ROOT_DIR}"
    "\nPolicy Dir:        ${policydir}"
    "\nSpool Dir:         ${spoolDir}"
    "\nLog Dir:           ${logDir}"
    "\n"
    "\n================================================================\n"
)

########################################################################
## Show warning when installing user is different from the one that configured

install(CODE "
    if (NOT $ENV{USER} STREQUAL \$ENV{USER})
        message(STATUS \"ATTENTION: Install is being performed by user \"
                \"'\$ENV{USER}', but the build directory was configured by \"
                \"user '$ENV{USER}'. This may result in a permissions error \"
                \"when writing the install manifest, but you can ignore it \"
                \"and consider the installation as successful if you don't \"
                \"care about the install manifest.\")
    endif ()
")
