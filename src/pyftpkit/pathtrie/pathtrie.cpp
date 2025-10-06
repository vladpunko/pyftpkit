// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#include <string_view>

#include "pathtrie.h"

namespace pyftpkit {

static std::vector<std::string_view> split(const std::string& str) {
    std::vector<std::string_view> parts;
    parts.reserve(PATHTRIE_PATHS_RESERVE); // avoids reallocations for small splits

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

PathTrie::PathTrie() : _root(std::make_unique<TrieNode>()) {}

const TrieNode* PathTrie::getRoot() const {
    return _root.get();
}

void PathTrie::clear() {
    _root = std::make_unique<TrieNode>();
}

TrieNode* PathTrie::insertPath(TrieNode* node, const std::string& path) {
    auto [it, inserted] = node->children.emplace(path, nullptr);
    if (inserted) {
        it->second = std::make_unique<TrieNode>();
    }

    return it->second.get();
}

void PathTrie::insert(const std::string& path) {
    if (path.empty()) {
        return;
    }

    TrieNode* node = _root.get();

    static const std::string sep(1, SEP);
    if (path.front() == SEP) {
        node = insertPath(node, sep);
    }

    static const std::string dot(".");
    for (const auto& part : split(path)) {
        if (part.empty() || part == dot) {
            continue;
        }
        node = insertPath(node, std::string(part));
    }
}

std::vector<std::string> PathTrie::getAllUniquePaths() const {
    std::vector<std::string> paths;
    paths.reserve(PATHTRIE_DEPTH_RESERVE);

    std::string buffer;
    buffer.reserve(PATHTRIE_PATHS_RESERVE);

    collectPaths(_root.get(), buffer, paths);

    return paths;
}

void PathTrie::collectPaths(
    const TrieNode* node, std::string& buffer, std::vector<std::string>& paths
) const {
    for (const auto& [name, child] : node->children) {
        size_t size = buffer.size();

        if (!buffer.empty() && buffer.back() != SEP) {
            buffer.push_back(SEP);
        }
        buffer.append(name);

        paths.push_back(buffer);
        collectPaths(child.get(), buffer, paths);

        buffer.resize(size);
    }
}

} // namespace pyftpkit
