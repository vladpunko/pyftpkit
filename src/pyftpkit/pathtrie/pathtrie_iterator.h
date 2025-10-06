// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#ifndef _PATHTRIE_ITERATOR_HEADER
#define _PATHTRIE_ITERATOR_HEADER

#include <memory>
#include <stack>
#include <string>
#include <unordered_map>

#include "pathtrie.h"

namespace pyftpkit {

struct StackFrame {
    const TrieNode* node;
    std::unordered_map<std::string, std::unique_ptr<TrieNode>>::const_iterator it;
    std::unordered_map<std::string, std::unique_ptr<TrieNode>>::const_iterator end;
    std::string prefix;
};

class PathTrieIterator {
public:
    PathTrieIterator(const PathTrie& trie);

    PathTrieIterator& iter();
    std::string next();

private:
    std::stack<StackFrame> _stack;

    std::string joinPath(const std::string& prefix, const std::string& part) const;
    void pushFrame(const TrieNode* node, const std::string& prefix);
};

} // namespace pyftpkit

#endif
