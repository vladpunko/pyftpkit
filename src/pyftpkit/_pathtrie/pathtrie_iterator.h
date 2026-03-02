// -*- coding: utf-8 -*-

// Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
// Created date: 2025-10-05

#ifndef PATHTRIE_ITERATOR_H_
#define PATHTRIE_ITERATOR_H_

#include <map>
#include <memory>
#include <stack>
#include <string>

#include "pathtrie.h"

namespace pyftpkit {

struct PathTrieStackFrame {
    const TrieNode *node;
    std::map<std::string, std::unique_ptr<TrieNode>>::const_iterator it;
    std::map<std::string, std::unique_ptr<TrieNode>>::const_iterator end;
    std::string prefix;
};

class PathTrieIterator {
public:
    virtual ~PathTrieIterator() = default;
    virtual PathTrieIterator &Iter();
    virtual std::string Next() = 0;

protected:
    std::stack<PathTrieStackFrame> stack_;

    std::string JoinPath(const std::string &prefix, const std::string &path_part) const;
    void PushFrame(const TrieNode *node, const std::string &prefix);
};

} // namespace pyftpkit

#endif
