// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#include <string_view>

#include "pathtrie.h"

namespace pyftpkit {

PathTrie::PathTrie() : _root(std::make_unique<TrieNode>()) {}

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

    static const std::string sep(1, _unixSep);
    if (path.front() == _unixSep) {
        node = insertPath(node, sep);
    }

    static const std::string dotChar("."); // "." and ".."
    for (const auto& part : split(path, _unixSep)) {
        if (part.empty() || part == dotChar) {
            continue;
        }
        node = insertPath(node, std::string(part));
    }
}

std::vector<std::string_view> PathTrie::split(
    const std::string& str, const char& sep
) {
    std::vector<std::string_view> parts;
    parts.reserve(_pathsReserve); // avoids reallocations for small splits

    size_t start = 0;
    size_t end = 0;

    while ((end = str.find(sep, start)) != std::string_view::npos) {
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

std::vector<std::string> PathTrie::getAllUniquePaths() const {
    std::vector<std::string> paths;
    paths.reserve(_depthReserve);

    std::string buffer;
    buffer.reserve(_pathsReserve);

    collectPaths(_root.get(), buffer, paths);

    return paths;
}

void PathTrie::collectPaths(
    const TrieNode* node, std::string& buffer, std::vector<std::string>& paths
) const {
    for (const auto& [name, child] : node->children) {
        size_t size = buffer.size();

        if (!buffer.empty() && buffer.back() != _unixSep) {
            buffer.push_back(_unixSep);
        }
        buffer.append(name);

        paths.push_back(buffer);
        collectPaths(child.get(), buffer, paths);

        buffer.resize(size);
    }
}

} // namespace pyftpkit
