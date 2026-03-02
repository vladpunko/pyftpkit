// -*- coding: utf-8 -*-

// Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
// Created date: 2026-03-03

#ifndef PATHTRIE_ITERATOR_POSTORDER_H_
#define PATHTRIE_ITERATOR_POSTORDER_H_

#include <string>

#include "pathtrie_iterator.h"

namespace pyftpkit {

class PathTrieIteratorPostOrder : public PathTrieIterator {
public:
    explicit PathTrieIteratorPostOrder(const PathTrie &trie);

    std::string Next() override;
};

} // namespace pyftpkit

#endif
