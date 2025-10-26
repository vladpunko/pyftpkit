// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#include <pybind11/pybind11.h>

#include "pathtrie_iterator.h"

namespace py = pybind11;

namespace pyftpkit {

PathTrieIterator::PathTrieIterator(const PathTrie &trie)
{
    const TrieNode *root = trie.root_.get();

    if (root && !root->children.empty()) {
        PushFrame(root, "");
    }
}

PathTrieIterator &
PathTrieIterator::Iter()
{
    return *this;
}

std::string
PathTrieIterator::JoinPath(const std::string &prefix, const std::string &path_part) const
{
    // Skip current directory references.
    if (path_part == ".") {
        return prefix;
    }

    // Handle parent directory reference.
    if (path_part == "..") {
        auto pos = prefix.find_last_of(PathTrie::kUnixSep);
        if (pos == std::string::npos || pos == 0) {
            return "/";
        }
        return prefix.substr(0, pos);
    }

    if (!prefix.empty() && prefix.back() != PathTrie::kUnixSep) {
        return prefix + PathTrie::kUnixSep + path_part;
    }

    return prefix + path_part;
}

void
PathTrieIterator::PushFrame(const TrieNode *node, const std::string &prefix)
{
    if (!node->children.empty()) {
        stack_.push({node, node->children.begin(), node->children.end(), prefix});
    }
}

std::string
PathTrieIterator::Next()
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

        if (path_part != "." && path_part != "..") {
            return path;
        }

        return path;
    }

    throw py::stop_iteration();
}

} // namespace pyftpkit
