// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pathtrie.h"
#include "pathtrie_iterator.h"

namespace py = pybind11;

PYBIND11_MODULE(_pathtrie, m) {
    m.doc() = "High-performance unique path generator using a trie.";

    py::class_<pyftpkit::PathTrieIterator>(m, "PathTrieIterator")
        .def("__iter__", &pyftpkit::PathTrieIterator::Iter, py::return_value_policy::reference_internal, "Returns self as an iterator.")
        .def("__next__", &pyftpkit::PathTrieIterator::Next, "Returns the next unique path string.");

    py::class_<pyftpkit::PathTrie>(m, "PathTrie")
        .def(py::init<>())
        .def("__iter__", [](pyftpkit::PathTrie &self) {
            // The iterator maintains references to elements within the trie.
            // Modifying the trie during iteration results in undefined behavior.
            return pyftpkit::PathTrieIterator(self);
        }, py::keep_alive<0, 1>(), "Returns all unique paths as a generator of strings. Do not mutate the trie while iterating.")
        .def("clear", &pyftpkit::PathTrie::Clear, "Clears the entire trie.")
        .def("insert", &pyftpkit::PathTrie::Insert, py::arg("path"), "Inserts a single path into a trie.")
        .def("get_all_unique_paths", &pyftpkit::PathTrie::GetAllUniquePaths, "Returns all unique paths as a list of strings.");
}
