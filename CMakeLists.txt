########################################################################
## CMake Configuration

cmake_minimum_required(VERSION 2.8 FATAL_ERROR)

# Prohibit in-source builds.
if ("${CMAKE_SOURCE_DIR}" STREQUAL "${CMAKE_BINARY_DIR}")
    message(FATAL_ERROR "In-source builds are not allowed. Please use "
                        "./configure to choose a build directory and "
                        "initialize the build configuration.")
endif ()

set(CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/cmake)

########################################################################
## Project/Build Configuration

project(broctl)

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

find_package(Bro REQUIRED)
if (NOT ${BRO_ROOT_DIR} STREQUAL ${CMAKE_INSTALL_PREFIX})
    message(WARNING "Broctl installation directory ${CMAKE_INSTALL_PREFIX} "
                    "does not match Bro installation directory ${BRO_ROOT_DIR}")
endif ()
find_package(PythonInterp REQUIRED)

if (EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/aux/pysubnettree/CMakeLists.txt)
    add_subdirectory(aux/pysubnettree)
    set(SubnetTree_FOUND true)
endif ()
find_package(SubnetTree REQUIRED)

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

########################################################################
## Generate/Configure files

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/bin/broctl.in
               ${CMAKE_CURRENT_BINARY_DIR}/bin/broctl)

########################################################################
## Install

# copy BroControl package to build dir and compile everything before install
install(CODE "execute_process(COMMAND ${CMAKE_COMMAND} -E copy_directory
        ${CMAKE_CURRENT_SOURCE_DIR}/BroControl
        ${CMAKE_CURRENT_BINARY_DIR}/BroControl)")
install(CODE "execute_process(COMMAND ${PYTHON_EXECUTABLE} -c
        \"import compileall; compileall.compile_dir('BroControl')\"
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})")

install(PROGRAMS ${CMAKE_CURRENT_BINARY_DIR}/bin/broctl
        DESTINATION bin)
install(DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/BroControl
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
    install(FILES policy/local/standalone.local.bro-template
            DESTINATION share/bro/site
            RENAME local.bro)
    install(FILES etc/node.cfg.standalone.in
            DESTINATION ${ETC}
            RENAME node.cfg)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg
            DESTINATION ${ETC}
            RENAME broctl.cfg)
    install(FILES etc/networks.cfg.in
            DESTINATION ${ETC}
            RENAME networks.cfg)
else ()
    configure_file(etc/broctl.cfg.cluster.in
                   ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg.example)
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
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/etc/broctl.cfg.example
            DESTINATION ${ETC})
    install(FILES etc/networks.cfg.in
            DESTINATION ${ETC}
            RENAME networks.cfg.example)
endif ()

install(DIRECTORY DESTINATION spool)
install(DIRECTORY DESTINATION spool/tmp)
install(DIRECTORY DESTINATION logs)

# The dynamic state will be updated on first `broctl install`
file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/broctl.dat)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/broctl.dat
        DESTINATION spool)

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