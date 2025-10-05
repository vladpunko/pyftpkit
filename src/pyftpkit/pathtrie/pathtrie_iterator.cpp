// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#include "pathtrie_iterator.h"

namespace py = pybind11;

namespace pyftpkit {

PathTrieIterator::PathTrieIterator(const PathTrie& trie) : index(0) {
    auto [buffer, slices] = trie.getAllUniquePaths();
    arena = std::move(buffer);
    views = std::move(slices);
}

PathTrieIterator& PathTrieIterator::iter() {
    return *this;
}

std::string PathTrieIterator::next() {
    if (index >= views.size()) {
        throw pybind11::stop_iteration();
    }

    return std::string(views[index++]); // cast only here with allocation
}

} // namespace pyftpkit
