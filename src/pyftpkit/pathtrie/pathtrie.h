// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#ifndef _PATHTRIE_HEADER
#define _PATHTRIE_HEADER

#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace pyftpkit {

constexpr char SEP = '/';
constexpr size_t PATHTRIE_DEPTH_RESERVE = 1 << 12; // estimated average path depth in the trie
constexpr size_t PATHTRIE_PATHS_RESERVE = 1 << 12; // expected number of unique paths

struct TrieNode {
    std::unordered_map<std::string, std::unique_ptr<TrieNode>> children;
};

class PathTrie {
public:
    PathTrie();

    const TrieNode* getRoot() const;
    void clear();
    void insert(const std::string& path);
    std::vector<std::string> getAllUniquePaths() const;

private:
    std::unique_ptr<TrieNode> _root;

    void collectPaths(
        const TrieNode* node, std::string& buffer, std::vector<std::string>& paths
    ) const;
    TrieNode* insertPath(TrieNode* node, const std::string& path);
};

} // namespace pyftpkit

#endif
