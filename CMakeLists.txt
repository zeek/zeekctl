project(Broctl)

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
    set(STANDALONE_BOOL "True")
    set(cfgType "Standalone")
else ()
    set(STANDALONE_BOOL "False")
    set(cfgType "Cluster")
endif ()

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

FindRequiredPackage(Bro)
FindRequiredPackage(PythonInterp)
FindRequiredPackage(SubnetTree)

if (MISSING_PREREQS)
    foreach (prereq ${MISSING_PREREQ_DESCS})
        message(SEND_ERROR ${prereq})
    endforeach ()
    message(FATAL_ERROR "Configuration aborted due to missing prerequisites")
endif ()

if (NOT ${BRO_ROOT_DIR} STREQUAL ${CMAKE_INSTALL_PREFIX})
    message(WARNING "Broctl installation directory ${CMAKE_INSTALL_PREFIX} "
                    "does not match Bro installation directory ${BRO_ROOT_DIR}")
endif ()

########################################################################
## Generate/Configure files

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/bin/broctl.in
               ${CMAKE_CURRENT_BINARY_DIR}/bin/broctl)

########################################################################
## Install

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

set(ETC etc)

if (PACKAGING_MODE AND ${CMAKE_SYSTEM_NAME} MATCHES "Linux")
    # Packaging for Apple-based systems does not go through all this
    # because many probably find it more convenient for uninstalling
    # when everything resides under a common prefix (since there's no
    # native package management system)

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
    execute_process(COMMAND "${CMAKE_COMMAND}" -E create_symlink
                  ${SPOOL}/broctl-config.sh
                  ${CMAKE_CURRENT_BINARY_DIR}/broctl-config.sh)
    # configure broctl.cfg point SpoolDir/LogDir to right runtime directories
    configure_file(etc/broctl.cfg.package.in
                   ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg)
else ()
    install(DIRECTORY DESTINATION spool)
    install(DIRECTORY DESTINATION spool/tmp)
    install(DIRECTORY DESTINATION spool/policy)
    install(DIRECTORY DESTINATION logs)
    execute_process(COMMAND "${CMAKE_COMMAND}" -E create_symlink
                  ${PREFIX}/spool/broctl-config.sh
                  ${CMAKE_CURRENT_BINARY_DIR}/broctl-config.sh)
    configure_file(etc/broctl.cfg.standalone.in
                   ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg)
endif ()

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/broctl-config.sh
        DESTINATION share/broctl/scripts)

install(FILES etc/analysis.dat DESTINATION ${ETC})
set(INSTALLED_CONFIG_FILES
    "${INSTALLED_CONFIG_FILES} ${PREFIX}/etc/analysis.dat"
    CACHE STRING "" FORCE)

if (STANDALONE)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg
            DESTINATION ${ETC}
            RENAME broctl.cfg)
    set(INSTALLED_CONFIG_FILES
        "${INSTALLED_CONFIG_FILES} ${PREFIX}/etc/broctl.cfg"
        CACHE STRING "" FORCE)

    # The policy file template is configured into build dir just
    # to assist running bro from the build directory
    configure_file(policy/local/standalone.local.bro-template
                   ${CMAKE_CURRENT_BINARY_DIR}/policy/local/local.bro
                   COPY_ONLY)
    install(FILES policy/local/standalone.local.bro-template
            DESTINATION share/bro/site
            RENAME local.bro)
    set(INSTALLED_CONFIG_FILES
        "${INSTALLED_CONFIG_FILES} ${PREFIX}/share/bro/site/local.bro"
        CACHE STRING "" FORCE)

    install(FILES etc/node.cfg.standalone.in
            DESTINATION ${ETC}
            RENAME node.cfg)
    install(FILES etc/networks.cfg.in
            DESTINATION ${ETC}
            RENAME networks.cfg)
    set(INSTALLED_CONFIG_FILES
        "${INSTALLED_CONFIG_FILES} ${PREFIX}/etc/node.cfg"
        CACHE STRING "" FORCE)
    set(INSTALLED_CONFIG_FILES
        "${INSTALLED_CONFIG_FILES} ${PREFIX}/etc/networks.cfg"
        CACHE STRING "" FORCE)
else ()
    configure_file(etc/broctl.cfg.cluster.in
                   ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg.example)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg.example
            DESTINATION ${ETC})

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
    install(FILES policy/local/cluster.local.bro-template
            DESTINATION share/bro/site
            RENAME local.bro)
    install(FILES policy/local/cluster.local-worker.bro-template
            DESTINATION share/bro/site
            RENAME local-worker.bro)
    install(FILES policy/local/cluster.local-manager.bro-template
            DESTINATION share/bro/site
            RENAME local-manager.bro)
    set(INSTALLED_CONFIG_FILES
        "${INSTALLED_CONFIG_FILES} ${PREFIX}/share/bro/site/local.bro"
        CACHE STRING "" FORCE)
    set(INSTALLED_CONFIG_FILES
        "${INSTALLED_CONFIG_FILES} ${PREFIX}/share/bro/site/local-worker.bro"
        CACHE STRING "" FORCE)
    set(INSTALLED_CONFIG_FILES
        "${INSTALLED_CONFIG_FILES} ${PREFIX}/share/bro/site/local-manager.bro"
        CACHE STRING "" FORCE)

    install(FILES etc/node.cfg.cluster.in
            DESTINATION ${ETC}
            RENAME node.cfg.example)
    install(FILES etc/networks.cfg.in
            DESTINATION ${ETC}
            RENAME networks.cfg.example)
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

message(
    "\n=================|  Broctl Install Summary  |==================="
    "\n"
    "\nInstall prefix:    ${CMAKE_INSTALL_PREFIX}"
    "\nConfiguration:     ${cfgType}"
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
