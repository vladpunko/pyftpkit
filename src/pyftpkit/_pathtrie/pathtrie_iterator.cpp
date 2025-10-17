// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#include <pybind11/pybind11.h>

#include "pathtrie_iterator.h"

namespace py = pybind11;

namespace pyftpkit {

PathTrieIterator::PathTrieIterator(const PathTrie& trie) {
    const TrieNode* root = trie._root.get();

    if (root && !root->children.empty()) {
        pushFrame(root, "");
    }
}

PathTrieIterator& PathTrieIterator::iter() {
    return *this;
}

std::string PathTrieIterator::joinPath(
    const std::string& prefix, const std::string& part
) const {
    if (!prefix.empty() && prefix.back() != PathTrie::_unixSep) {
        return prefix + PathTrie::_unixSep + part;
    }

    return prefix + part;
}

void PathTrieIterator::pushFrame(const TrieNode* node, const std::string& prefix) {
    if (!node->children.empty()) {
        _stack.push({node, node->children.begin(), node->children.end(), prefix});
    }
}

std::string PathTrieIterator::next() {
    while (!_stack.empty()) {
        auto& top = _stack.top();

        if (top.it == top.end) {
            _stack.pop();

            continue;
        }

        const auto& part = top.it->first;
        const TrieNode* child = top.it->second.get();
        ++top.it; // move to the next child

        std::string path = joinPath(top.prefix, part);
        pushFrame(child, path);

        return path;
    }

    throw py::stop_iteration();
}

} // namespace pyftpkit
