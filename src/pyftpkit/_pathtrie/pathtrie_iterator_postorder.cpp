// -*- coding: utf-8 -*-

// Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
// Created date: 2026-03-03

#include <pybind11/pybind11.h>

#include "pathtrie_iterator_postorder.h"

namespace py = pybind11;

namespace pyftpkit {

PathTrieIteratorPostOrder::PathTrieIteratorPostOrder(const PathTrie &trie)
{
    const TrieNode *root = trie.root_.get();

    if (!root) {
        return;
    }

    PushFrame(root, "");
}

std::string
PathTrieIteratorPostOrder::Next()
{
    while (!stack_.empty()) {
        auto &top = stack_.top();

        if (top.it == top.end) {
            std::string path = top.prefix;
            stack_.pop();

            if (!path.empty()) {
                return path;
            }

            continue;
        }

        const auto &path_part = top.it->first;
        const TrieNode *child = top.it->second.get();
        ++top.it; // advance parent iterator

        std::string path = JoinPath(top.prefix, path_part);
        PushFrame(child, path);
    }

    throw py::stop_iteration();
}

} // namespace pyftpkit
