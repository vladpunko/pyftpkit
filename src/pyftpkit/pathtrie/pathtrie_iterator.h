// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#ifndef _PATHTRIE_ITERATOR_HEADER
#define _PATHTRIE_ITERATOR_HEADER

#include <memory>
#include <string_view>
#include <string>
#include <vector>

#include <pybind11/pybind11.h>

#include "pathtrie.h"

namespace pyftpkit {

class PathTrieIterator {
public:
    PathTrieIterator(const PathTrie& trie);

    PathTrieIterator& iter();
    std::string next();

private:
    size_t index;
    std::shared_ptr<std::string> arena;
    std::vector<std::string_view> views;
};

} // namespace pyftpkit

#endif
