// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#include "pathtrie.h"

namespace pyftpkit {

static std::vector<std::string_view> split(const std::string& str) {
    std::vector<std::string_view> parts;
    parts.reserve(PATH_TRIE_PATHS_RESERVE); // avoids reallocations for small splits

    size_t start = 0;
    size_t end = 0;

    while ((end = str.find(SEP, start)) != std::string_view::npos) {
        if (end > start) {
            parts.emplace_back(std::string_view(str.data() + start, end - start));
        }
        start = end + 1;
    }

    if (start < str.size()) {
        parts.emplace_back(std::string_view(str.data() + start, str.size() - start));
    }

    return parts;
}

PathTrie::PathTrie() : root(std::make_unique<TrieNode>()) {
    storage.resize(PATH_TRIE_PATHS_RESERVE);
}

void PathTrie::clear() {
    root = std::make_unique<TrieNode>();

    storage.clear();
}

TrieNode* PathTrie::insertPath(TrieNode* node, const std::string_view& path) {
    auto iter = node->children.find(path);

    if (iter != node->children.end()) {
        return iter->second.get();
    }

    storage.emplace_back(path);
    auto& next = node->children[storage.back()];
    next = std::make_unique<TrieNode>();

    return next.get();
}

void PathTrie::insert(const std::string& path) {
    TrieNode* node = root.get();

    if (!path.empty() && path.front() == SEP) {
        node = insertPath(node, std::string(1, SEP));
    }

    auto parts = split(path);
    for (const auto& part : parts) {
        static const std::string dot = ".";
        if (part.empty() || part == dot) {
            continue;
        }
        node = insertPath(node, part);
    }
}

UniquePaths PathTrie::getAllUniquePaths() const {
    auto arena = std::make_shared<std::string>();
    arena->reserve(PATH_TRIE_ARENA_RESERVE);

    std::vector<std::string_view> views;
    views.reserve(PATH_TRIE_VIEWS_RESERVE);

    std::string buffer;
    buffer.reserve(PATH_TRIE_PATHS_RESERVE);

    collectPaths(root.get(), buffer, *arena, views);

    return {arena, views};
}

void PathTrie::collectPaths(
    const TrieNode* node,
    std::string& buffer,
    std::string& arena,
    std::vector<std::string_view>& views
) const {
    static const char terminator = '\0';

    for (const auto& [name, child] : node->children) {
        size_t size = buffer.size();

        if (!buffer.empty() && buffer.back() != SEP) {
            buffer += SEP;
        }
        buffer += name;

        size_t start = arena.size();
        arena.append(buffer);
        arena.push_back(terminator);
        views.emplace_back(arena.data() + start, buffer.size());

        collectPaths(child.get(), buffer, arena, views);

        buffer.resize(size);
    }
}

} // namespace pyftpkit
