// -*- coding: utf-8 -*-

// Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
// Created date: 2025-10-05

#ifndef PATHTRIE_H_
#define PATHTRIE_H_

#include <map>
#include <memory>
#include <string>
#include <vector>

namespace pyftpkit {

struct TrieNode {
    std::map<std::string, std::unique_ptr<TrieNode>> children;
};

// Use the forward declaration for this class and declare it as a friend of the
// class containing the trie to encapsulate and hide as many attributes as possible.
class PathTrieIterator;

class PathTrie {
public:
    PathTrie();

    void Clear();
    void Insert(const std::string &path);
    std::vector<std::string> GetAllUniquePaths() const;

private:
    std::unique_ptr<TrieNode> root_;

    static constexpr char kUnixSep = '/';
    static constexpr size_t kPathLengthReserve = 1 << 12;  // estimated average path length (chars)
    static constexpr size_t kPathsReserve = 1 << 12;       // expected number of unique paths

    void CollectPaths(const TrieNode *node,
                      std::string &buffer,
                      std::vector<std::string> &paths) const;
    TrieNode *InsertPath(TrieNode *node, const std::string &path);
    static std::vector<std::string_view> SplitPath(const std::string &str, const char &sep);

    friend class PathTrieIterator;
};

} // namespace pyftpkit

#endif
