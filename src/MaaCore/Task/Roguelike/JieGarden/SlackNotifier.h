#pragma once

#include "Utils/Logger.hpp"
#include "Utils/StringMisc.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>

namespace asst
{

inline std::string get_slack_webhook_url()
{
    // 1. Try environment variable
    if (const char* env_url = std::getenv("SLACK_WEBHOOK_URL")) {
        std::string s = env_url;
        utils::string_trim(s);
        if (!s.empty()) {
            return s;
        }
    }

    // 2. Fallback: parse ~/.zprofile directly (needed for macOS GUI apps not launched from terminal)
    const char* home = std::getenv("HOME");
    if (!home) {
        return {};
    }
    std::filesystem::path zprofile_path = std::filesystem::path(home) / ".zprofile";
    std::ifstream ifs(zprofile_path);
    if (!ifs.is_open()) {
        return {};
    }

    std::string line;
    while (std::getline(ifs, line)) {
        utils::string_trim(line);
        if (line.starts_with("#")) {
            continue;
        }
        if (line.starts_with("export ")) {
            line = line.substr(7);
            utils::string_trim(line);
        }
        if (line.starts_with("SLACK_WEBHOOK_URL=")) {
            std::string val = line.substr(18);
            utils::string_trim(val);
            if ((val.starts_with("\"") && val.ends_with("\"")) ||
                (val.starts_with("'") && val.ends_with("'"))) {
                val = val.substr(1, val.length() - 2);
            }
            return val;
        }
    }
    return {};
}

inline void send_slack_notification(const std::string& text)
{
    std::string webhook_url = get_slack_webhook_url();
    if (webhook_url.empty()) {
        LogWarn << "[SlackNotifier] SLACK_WEBHOOK_URL not set in env or ~/.zprofile, skipping Slack notification";
        return;
    }

    LogInfo << "[SlackNotifier] Sending Slack webhook notification...";
    std::string escaped_text = text;
    utils::string_replace_all_in_place(escaped_text, "\\", "\\\\");
    utils::string_replace_all_in_place(escaped_text, "\"", "\\\"");

    std::string curl_cmd =
        "/usr/bin/curl -s --request POST --header 'Content-type: application/json' "
        "--data '{\"text\":\"" +
        escaped_text +
        "\"}' "
        "--location '" + webhook_url + "'";
    int ret = std::system(curl_cmd.c_str());
    LogInfo << "[SlackNotifier] Slack webhook sent, exit code:" << ret;
}

} // namespace asst
