// -*- coding: utf-8 -*-

// Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
// Created date: 2026-03-03

#include <pybind11/pybind11.h>

#include "pathtrie_iterator_preorder.h"

namespace py = pybind11;

namespace pyftpkit {

PathTrieIteratorPreOrder::PathTrieIteratorPreOrder(const PathTrie &trie)
{
    const TrieNode *root = trie.root_.get();

    if (!root || root->children.empty()) {
        return;
    }

    PushFrame(root, "");
}

std::string
PathTrieIteratorPreOrder::Next()
{
    while (!stack_.empty()) {
        auto &top = stack_.top();

        if (top.it == top.end) {
            stack_.pop();

            continue;
        }

        const auto &path_part = top.it->first;
        const TrieNode *child = top.it->second.get();
        ++top.it; // move to the next child

        std::string path = JoinPath(top.prefix, path_part);
        PushFrame(child, path);

        if (path_part != PathTrie::kUnixCurDir && path_part != PathTrie::kUnixParDir) {
            return path;
        }

        return path;
    }

    throw py::stop_iteration();
}

} // namespace pyftpkit
