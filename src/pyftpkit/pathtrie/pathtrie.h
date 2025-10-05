// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#ifndef _PATHTRIE_HEADER
#define _PATHTRIE_HEADER

#include <deque>
#include <memory>
#include <string_view>
#include <string>
#include <unordered_map>
#include <vector>

// arena allocation
#define PATH_TRIE_ARENA_RESERVE 4096 // bytes for arena string storage

// vector preallocation
#define PATH_TRIE_VIEWS_RESERVE 128 // estimated average path depth in the trie
#define PATH_TRIE_PATHS_RESERVE 256 // expected number of unique paths

namespace pyftpkit {

static const char SEP = '/';

using UniquePaths = std::pair<std::shared_ptr<std::string>, std::vector<std::string_view>>;

struct TrieNode {
    std::unordered_map<std::string_view, std::unique_ptr<TrieNode>> children;
};

class PathTrie {
public:
    PathTrie();

    void clear();
    void insert(const std::string& path);
    UniquePaths getAllUniquePaths() const;

private:
    std::unique_ptr<TrieNode> root;
    std::deque<std::string> storage; // arena for strings

    void collectPaths(
        const TrieNode* node,
        std::string& buffer,
        std::string& arena,
        std::vector<std::string_view>& views
    ) const;
    TrieNode* insertPath(TrieNode* node, const std::string_view& path);
};

} // namespace pyftpkit

#endif
