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
            // To avoid undefined behavior, ensure that all collected paths
            // remain valid in memory for the entire lifetime of the iterator.
            // By creating a dedicated iterator object, we guarantee that the
            // underlying data persists safely until iteration completes or
            // the generator is destroyed.
            return pyftpkit::PathTrieIterator(self);
        }, py::keep_alive<0, 1>(), "Returns all unique paths as a generator of strings.")
        .def("clear", &pyftpkit::PathTrie::Clear, "Clears the entire trie.")
        .def("insert", &pyftpkit::PathTrie::Insert, py::arg("path"), "Inserts a single path into a trie.")
        .def("get_all_unique_paths", &pyftpkit::PathTrie::GetAllUniquePaths, "Returns all unique paths as a list of strings.");
}
