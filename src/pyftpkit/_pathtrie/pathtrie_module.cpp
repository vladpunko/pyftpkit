// -*- coding: utf-8 -*-

// Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
// Created date: 2025-10-05

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pathtrie.h"
#include "pathtrie_iterator_preorder.h"
#include "pathtrie_iterator_postorder.h"

namespace py = pybind11;

PYBIND11_MODULE(_pathtrie, m) {
    m.doc() = "High-performance unique path generator using a trie.";

    py::class_<pyftpkit::PathTrieIterator>(m, "PathTrieIterator")
        .def("__iter__", &pyftpkit::PathTrieIterator::Iter, py::return_value_policy::reference_internal, "Returns self as an iterator.");

    py::class_<pyftpkit::PathTrieIteratorPreOrder, pyftpkit::PathTrieIterator>(m, "PathTrieIteratorPreOrder")
        .def("__next__", &pyftpkit::PathTrieIteratorPreOrder::Next, "Returns the next unique path string.");

    py::class_<pyftpkit::PathTrieIteratorPostOrder, pyftpkit::PathTrieIterator>(m, "PathTrieIteratorPostOrder")
        .def("__next__", &pyftpkit::PathTrieIteratorPostOrder::Next, "Returns the next unique path string in post-order.");

    py::class_<pyftpkit::PathTrie>(m, "PathTrie")
        .def(py::init<>())
        .def("__iter__", [](pyftpkit::PathTrie &self) {
            // The iterator maintains references to elements within the trie.
            // Modifying the trie during iteration results in undefined behavior.
            return pyftpkit::PathTrieIteratorPreOrder(self);
        }, py::keep_alive<0, 1>(), "Returns an iterator over all unique paths. Do not mutate the trie while iterating.")
        .def("__reversed__", [](pyftpkit::PathTrie &self) {
            // Reverse iteration yields paths in post-order (children before parents).
            return pyftpkit::PathTrieIteratorPostOrder(self);
        }, py::keep_alive<0, 1>(), "Returns an iterator over all unique paths in post-order. Do not mutate the trie while iterating.")
        .def("clear", &pyftpkit::PathTrie::Clear, "Clears the entire trie.")
        .def("insert", &pyftpkit::PathTrie::Insert, py::arg("path"), "Inserts a single path into a trie.")
        .def("get_all_unique_paths", &pyftpkit::PathTrie::GetAllUniquePaths, "Returns all unique paths as a list of strings.");
}
