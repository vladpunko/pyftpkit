cmake_minimum_required(VERSION 3.15)
project(pathtrie C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(libs/pybind11)

set(PYTHON_MODULE_OUTPUT_DIR "${CMAKE_SOURCE_DIR}/src/pyftpkit/pathtrie")

pybind11_add_module(pathtrie
    src/pyftpkit/pathtrie/pathtrie_iterator.cpp
    src/pyftpkit/pathtrie/pathtrie_module.cpp
    src/pyftpkit/pathtrie/pathtrie.cpp
)

set_target_properties(pathtrie PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${PYTHON_MODULE_OUTPUT_DIR}"
)
