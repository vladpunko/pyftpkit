// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#ifndef _PATHTRIE_HEADER
#define _PATHTRIE_HEADER

#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace pyftpkit {

struct TrieNode {
    std::unordered_map<std::string, std::unique_ptr<TrieNode>> children;
};

// Use a forward declaration for this class and declare it as a friend of the
// class containing the trie to encapsulate and hide as many attributes as possible.
class PathTrieIterator;

class PathTrie {
public:
    PathTrie();

    void clear();
    void insert(const std::string& path);
    std::vector<std::string> getAllUniquePaths() const;

private:
    std::unique_ptr<TrieNode> _root;

    void collectPaths(
        const TrieNode* node, std::string& buffer, std::vector<std::string>& paths
    ) const;
    TrieNode* insertPath(TrieNode* node, const std::string& path);

    static constexpr char _unixSep = '/';
    static constexpr size_t _depthReserve = 1 << 12; // estimated average path depth in the trie
    static constexpr size_t _pathsReserve = 1 << 12; // expected number of unique paths
    static std::vector<std::string_view> split(const std::string& str, const char& sep);

    friend class PathTrieIterator;
};

} // namespace pyftpkit

#endif
