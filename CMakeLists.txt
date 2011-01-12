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

# if the install prefix of /usr was given, change the install location
# of the config file to be /etc instead of /usr/etc
if (${CMAKE_INSTALL_PREFIX} STREQUAL /usr)
    set(ETC /etc)
else ()
    set(ETC etc)
endif ()

set(policydir ${BRO_ROOT_DIR}/share/bro)

install(FILES etc/analysis.dat
        DESTINATION ${ETC})

if (STANDALONE)
    configure_file(etc/broctl.cfg.standalone.in
                   ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg
            DESTINATION ${ETC}
            RENAME broctl.cfg)

    # The policy file template is configured into build dir just
    # to assist running bro from the build directory
    configure_file(policy/local/standalone.local.bro-template
                   ${CMAKE_CURRENT_BINARY_DIR}/policy/local/local.bro
                   COPY_ONLY)
    install(FILES policy/local/standalone.local.bro-template
            DESTINATION share/bro/site
            RENAME local.bro)

    install(FILES etc/node.cfg.standalone.in
            DESTINATION ${ETC}
            RENAME node.cfg)
    install(FILES etc/networks.cfg.in
            DESTINATION ${ETC}
            RENAME networks.cfg)
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

    install(FILES etc/node.cfg.cluster.in
            DESTINATION ${ETC}
            RENAME node.cfg.example)
    install(FILES etc/networks.cfg.in
            DESTINATION ${ETC}
            RENAME networks.cfg.example)
endif ()

install(DIRECTORY DESTINATION spool)
install(DIRECTORY DESTINATION spool/tmp)
install(DIRECTORY DESTINATION spool/policy)
install(DIRECTORY DESTINATION logs)

execute_process(COMMAND "${CMAKE_COMMAND}" -E create_symlink
              ${PREFIX}/spool/broctl-config.sh
              ${CMAKE_CURRENT_BINARY_DIR}/broctl-config.sh)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/broctl-config.sh
        DESTINATION ${PREFIX}/share/broctl/scripts)

########################################################################
## Packaging Setup

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
