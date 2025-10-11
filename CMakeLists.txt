cmake_minimum_required(VERSION 3.8)

set(MODULE_NAME "_pathtrie")
project(${MODULE_NAME})

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(libs/pybind11)

pybind11_add_module(${MODULE_NAME}
    src/pyftpkit/pathtrie/pathtrie_iterator.cpp
    src/pyftpkit/pathtrie/pathtrie_module.cpp
    src/pyftpkit/pathtrie/pathtrie.cpp
)
