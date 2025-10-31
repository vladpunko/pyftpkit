cmake_minimum_required(VERSION 3.15)

set(PACKAGE_NAME "pyftpkit")
set(MODULE_NAME "_pathtrie")
project(${MODULE_NAME})

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(${MODULE_NAME}
    src/${PACKAGE_NAME}/_pathtrie/pathtrie_iterator.cpp
    src/${PACKAGE_NAME}/_pathtrie/pathtrie_module.cpp
    src/${PACKAGE_NAME}/_pathtrie/pathtrie.cpp
)

target_compile_options(${MODULE_NAME} PRIVATE
    -Wall
    -Wextra
    -Werror
    -Wno-unused-parameter
)
target_link_libraries(${MODULE_NAME} PRIVATE pybind11::headers)

install(TARGETS ${MODULE_NAME} DESTINATION ${PACKAGE_NAME})
