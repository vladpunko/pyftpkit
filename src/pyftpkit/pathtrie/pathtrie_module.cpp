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
        .def("__iter__", &pyftpkit::PathTrieIterator::iter, py::keep_alive<0, 1>(), "Returns self as an iterator.")
        .def("__next__", &pyftpkit::PathTrieIterator::next, "Returns the next unique path string.");

    py::class_<pyftpkit::PathTrie>(m, "PathTrie")
        .def(py::init<>())
        .def("__iter__", [](pyftpkit::PathTrie &self) {
            // To avoid problems with undefined behavior, it is necessary to keep the collected
            // paths in memory until the generator is either deallocated or stopped. To do this, it is
            // better to create an additional iterator, since after calling this method, the lambda
            // function will be destroyed.
            return pyftpkit::PathTrieIterator(self);
        }, py::keep_alive<0, 1>(), "Returns all unique paths as a generator of strings.")
        .def("clear", &pyftpkit::PathTrie::clear, "Clears the entire trie.")
        .def("insert", &pyftpkit::PathTrie::insert, py::arg("path"), "Inserts a single path into a trie.");
}
