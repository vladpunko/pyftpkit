// -*- coding: utf-8 -*-

// Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

#include <string_view>

#include "pathtrie.h"

namespace pyftpkit {

PathTrie::PathTrie() : root_(std::make_unique<TrieNode>()) {}

void
PathTrie::Clear()
{
    root_ = std::make_unique<TrieNode>();
}

TrieNode *
PathTrie::InsertPath(TrieNode *node, const std::string &path)
{
    auto [it, inserted] = node->children.emplace(path, nullptr);
    if (inserted) {
        it->second = std::make_unique<TrieNode>();
    }

    return it->second.get();
}

void
PathTrie::Insert(const std::string &path)
{
    if (path.empty()) {
        return;
    }

    TrieNode *node = root_.get();

    static const std::string sep(1, kUnixSep);
    if (path.front() == kUnixSep) {
        node = InsertPath(node, sep);
    }

    for (const auto &part : SplitPath(path, kUnixSep)) {
        if (part.empty() || part == ".") {  // "." and ".."
            continue;
        }
        node = InsertPath(node, std::string(part));
    }
}

std::vector<std::string_view>
PathTrie::SplitPath(const std::string &str, const char &sep)
{
    std::vector<std::string_view> parts;
    parts.reserve(kPathsReserve);  // avoid reallocations for small splits

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

std::vector<std::string>
PathTrie::GetAllUniquePaths() const
{
    std::vector<std::string> paths;
    paths.reserve(kDepthReserve);

    std::string buffer;
    buffer.reserve(kPathsReserve);

    CollectPaths(root_.get(), buffer, paths);

    return paths;
}

void
PathTrie::CollectPaths(const TrieNode *node,
                       std::string &buffer,
                       std::vector<std::string> &paths) const
{
    for (const auto &[name, child] : node->children) {
        size_t size = buffer.size();

        if (!buffer.empty() && buffer.back() != kUnixSep) {
            buffer.push_back(kUnixSep);
        }
        buffer.append(name);

        paths.push_back(buffer);
        CollectPaths(child.get(), buffer, paths);

        buffer.resize(size);
    }
}

} // namespace pyftpkit
