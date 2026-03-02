// -*- coding: utf-8 -*-

// Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
// Created date: 2025-10-05

#include "pathtrie_iterator.h"

namespace pyftpkit {

PathTrieIterator &
PathTrieIterator::Iter()
{
    return *this;
}

std::string
PathTrieIterator::JoinPath(const std::string &prefix, const std::string &path_part) const
{
    if (path_part == PathTrie::kUnixCurDir) {
        return prefix;
    }

    if (path_part == PathTrie::kUnixParDir) {
        auto pos = prefix.find_last_of(*PathTrie::kUnixSep);
        if (pos == std::string::npos || pos == 0) {
            return PathTrie::kUnixSep;
        }
        return prefix.substr(0, pos);
    }

    if (!prefix.empty() && prefix.back() != *PathTrie::kUnixSep) {
        return prefix + *PathTrie::kUnixSep + path_part;
    }

    return prefix + path_part;
}

void
PathTrieIterator::PushFrame(const TrieNode *node, const std::string &prefix)
{
    stack_.push({node, node->children.begin(), node->children.end(), prefix});
}

} // namespace pyftpkit
