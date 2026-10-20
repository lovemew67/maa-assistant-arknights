#include "RoguelikeSuiShiTaskPlugin.h"

#include "Common/AsstTypes.h"
#include "Config/TaskData.h"
#include "Controller/Controller.h"
#include "Task/ProcessTask.h"
#include "Utils/Logger.hpp"
#include "Utils/StringMisc.hpp"
#include "Vision/OCRer.h"
#include "TradSimpHelper.h"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <opencv2/core.hpp>

namespace asst
{

struct SuiShiDefinition
{
    std::string name;
    std::string verse;
    std::string patron;
    std::vector<std::string> keywords;
};

static const std::vector<SuiShiDefinition> ALL_SUISHI_DEFINITIONS = {
    { "子武", "敬刻一道破勇力，入时者畏惧退避", "重岳", { "子武", "一道破勇力", "破勇力", "畏惧退避", "畏懼退避", "承名重岳" } },
    { "丑谋", "敬刻二思算八方，入时者移步尽失", "望", { "丑谋", "丑謀", "二思算八方", "思算八方", "移步尽失", "移步盡失", "承名为望", "承名為望", "承名望" } },
    { "寅诗", "敬刻三白日逍遥，入时者所思非人", "令", { "寅诗", "寅詩", "三白日逍遥", "三白日逍遙", "白日逍遥", "白日逍遙", "所思非人", "承名为令", "承名為令", "承名令" } },
    { "卯律", "敬刻四天音传法，入时者难逾规矩", "均", { "卯律", "四天音传法", "四天音傳法", "天音传法", "天音傳法", "难逾规矩", "難逾規矩", "承名为均", "承名為均", "承名均" } },
    { "辰■", "敬刻五授道解惑，入时者不分■■", "颉", { "五授道解惑", "授道解惑", "不分", "承名为颉", "承名為頡", "承名颉", "承名頡" } },
    { "巳农", "敬刻六谷稻丰足，入时者朴食多餐", "黍", { "巳农", "巳農", "六谷稻丰足", "六穀稻豐足", "谷稻丰足", "穀稻豐足", "朴食多餐", "樸食多餐", "承名为黍", "承名為黍", "承名黍" } },
    { "午商", "敬刻七长绢聚富，入时者不知财数", "绩", { "午商", "七长绢聚富", "七長絹聚富", "长绢聚富", "長絹聚富", "不知财数", "不知財數", "承名为绩", "承名為績", "承名绩", "承名績" } },
    { "未建", "敬刻八筑巧藏珍，入时者流连难返", "易", { "未建", "八筑巧藏珍", "八築巧藏珍", "筑巧藏珍", "築巧藏珍", "流连难返", "流連難返", "承名为易", "承名為易", "承名易" } },
    { "申铸", "敬刻九铸金熔火，入时者得见其妙", "年", { "申铸", "申鑄", "九铸金熔火", "九鑄金熔火", "铸金熔火", "鑄金熔火", "得见其妙", "得見其妙", "承名为年", "承名為年", "承名年" } },
    { "酉疗", "敬刻十抚伤愈痕，入时者以眠抗害", "方", { "酉疗", "酉療", "十抚伤愈痕", "十撫傷愈痕", "抚伤愈痕", "撫傷愈痕", "以眠抗害", "承名为方", "承名為方", "承名方" } },
    { "戌绘", "敬刻十一卷生花，入时者皆赏便符", "夕", { "戌绘", "戌繪", "十一卷生花", "卷生花", "皆赏便符", "皆賞便符", "承名为夕", "承名為夕", "承名夕" } },
    { "亥食", "敬刻十二催饭香，入时亲属饱肚肠", "余", { "亥食", "十二催饭香", "十二催飯香", "催饭香", "催飯香", "饱肚肠", "飽肚腸", "承名为余", "承名為余", "承名余" } }
};

static std::string get_slack_webhook_url()
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

bool RoguelikeSuiShiTaskPlugin::verify(AsstMsg msg, const json::value& details) const
{
    if (msg != AsstMsg::SubTaskStart || details.get("subtask", std::string()) != "ProcessTask") {
        return false;
    }

    if (m_config->get_theme() != RoguelikeTheme::JieGarden) {
        return false;
    }

    const std::string roguelike_name = m_config->get_theme() + "@";
    const std::string& task = details.get("details", "task", "");
    std::string_view task_view = task;
    if (task_view.starts_with(roguelike_name)) {
        task_view.remove_prefix(roguelike_name.length());
    }

    if (task_view == "Roguelike@TestStrategyLogSuiShi" || task_view == "Roguelike@TestStrategyLogYiTraderGoods") {
        m_current_task = std::string(task_view);
        return true;
    }

    if (m_config->get_mode() == RoguelikeMode::TestStrategy && m_saved_suishi.empty()) {
        if (task_view.ends_with("NextLevel") || task_view.ends_with("CloseCollectionContinue") ||
            task_view.ends_with("StrategyChange")) {
            cv::Mat image = ctrler()->get_image();
            std::string detected = detect_suishi_from_image(image);
            if (!detected.empty()) {
                m_saved_suishi = std::move(detected);
                LogInfo << __FUNCTION__ << "captured SuiShi during transition:" << m_saved_suishi;
            }
        }
    }

    return false;
}

void RoguelikeSuiShiTaskPlugin::reset_in_run_variables()
{
    m_saved_suishi.clear();
    m_current_task.clear();
}

std::string RoguelikeSuiShiTaskPlugin::detect_suishi_from_image(const cv::Mat& image) const
{
    if (image.empty()) {
        return {};
    }

    OCRer analyzer(image);
    auto results_opt = analyzer.analyze();
    if (!results_opt || results_opt->empty()) {
        return {};
    }

    std::string full_text;
    for (const auto& item : *results_opt) {
        full_text += item.text;
    }

    std::string level;
    if (full_text.find("醒觉") != std::string::npos || full_text.find("醒覺") != std::string::npos) {
        level = "醒觉";
    }
    else if (full_text.find("入髓") != std::string::npos) {
        level = "入髓";
    }
    else if (full_text.find("真切") != std::string::npos) {
        level = "真切";
    }
    else if (full_text.find("朦胧") != std::string::npos || full_text.find("朦朧") != std::string::npos) {
        level = "朦胧";
    }

    for (const auto& suishi : ALL_SUISHI_DEFINITIONS) {
        for (const auto& kw : suishi.keywords) {
            if (full_text.find(kw) != std::string::npos) {
                std::string res = suishi.name;
                if (!level.empty()) {
                    res += "（" + level + "）";
                }
                res += " - " + suishi.verse;
                return res;
            }
        }
    }

    return {};
}

bool RoguelikeSuiShiTaskPlugin::_run()
{
    LogTraceFunction;

    if (m_current_task == "Roguelike@TestStrategyLogYiTraderGoods") {
        m_current_task.clear();
        return log_yitrader_goods();
    }
    m_current_task.clear();

    std::string detected = m_saved_suishi;
    if (detected.empty()) {
        cv::Mat image = ctrler()->get_image();
        detected = detect_suishi_from_image(image);
    }

    if (detected.empty()) {
        LogInfo << __FUNCTION__ << "SuiShi not visible on screen, trying to open SuiShi detail popup from top bar...";
        ctrler()->click(Point(718, 25));
        sleep(600);
        cv::Mat popup_image = ctrler()->get_image();
        detected = detect_suishi_from_image(popup_image);

        // 点击空白处关闭详情弹窗
        ctrler()->click(Point(640, 450));
        sleep(300);
    }

    if (!detected.empty()) {
        LogInfo << "========================================";
        LogInfo << "[JieGarden TestStrategy] Current SuiShi:" << detected;
        LogInfo << "========================================";
        callback(
            AsstMsg::SubTaskExtraInfo,
            json::object { { "task", "TestStrategyLogSuiShi" },
                           { "what", "SuiShiDetected" },
                           { "details", json::object { { "suishi", detected } } } });
    }
    else {
        LogInfo << "========================================";
        LogInfo << "[JieGarden TestStrategy] Current SuiShi: None detected at Floor 2 (current difficulty may not have SuiShi)";
        LogInfo << "========================================";
    }

    m_saved_suishi.clear();
    return true;
}

bool RoguelikeSuiShiTaskPlugin::log_yitrader_goods()
{
    LogTraceFunction;

    sleep(1000); // 等待货架与商品渲染完成
    cv::Mat image = ctrler()->get_image();
    if (image.empty()) {
        LogError << __FUNCTION__ << "Failed to capture image for YiTrader goods";
        return true;
    }

    OCRer analyzer(image);
    analyzer.set_task_info("RoguelikeTraderShoppingOcr");
    auto results_opt = analyzer.analyze();

    struct CandidateItem
    {
        std::string text;
        int x = 0;
    };
    std::vector<CandidateItem> candidates;

    if (results_opt && !results_opt->empty()) {
        for (const auto& item : *results_opt) {
            // 真正商品标题的 Y 坐标在 160 ~ 210（通常为 179~182），排除下方价格与按键区域
            if (item.rect.y < 160 || item.rect.y > 210) {
                continue;
            }

            std::string text = clean_and_simplify_product_name(item.text);
            if (text.empty()) {
                continue;
            }

            candidates.push_back({ std::move(text), item.rect.x });
        }
    }

    // 按横向位置从左到右排序（匹配货架格子顺序）
    std::sort(candidates.begin(), candidates.end(), [](const CandidateItem& a, const CandidateItem& b) {
        return a.x < b.x;
    });

    std::vector<std::string> goods_list;
    for (const auto& c : candidates) {
        if (std::find(goods_list.begin(), goods_list.end(), c.text) == goods_list.end()) {
            goods_list.push_back(c.text);
        }
    }

    std::string goods_str;
    if (goods_list.empty()) {
        goods_str = "None";
    }
    else {
        for (size_t i = 0; i < goods_list.size(); ++i) {
            if (i > 0) {
                goods_str += ", ";
            }
            goods_str += goods_list[i];
        }
    }

    LogInfo << "========================================";
    LogInfo << "[JieGarden TestStrategy] YiTrader goods for sale: " << goods_str;
    LogInfo << "========================================";

    json::array goods_arr;
    for (const auto& g : goods_list) {
        goods_arr.push_back(g);
    }
    callback(
        AsstMsg::SubTaskExtraInfo,
        json::object { { "task", "TestStrategyLogYiTraderGoods" },
                       { "what", "YiTraderGoodsDetected" },
                       { "details", json::object { { "goods", std::move(goods_arr) } } } });

    // 检查是否遇到目标稀有藏品："国王的新枪" / "扣挠之手"
    static const std::vector<std::string> TARGET_COLLECTIBLES = {
        "国王的新枪",
        "扣挠之手",
    };

    std::string matched_collectible;
    for (const auto& g : goods_list) {
        for (const auto& target : TARGET_COLLECTIBLES) {
            if (g.find(target) != std::string::npos) {
                matched_collectible = target;
                break;
            }
        }
        if (!matched_collectible.empty()) {
            break;
        }
    }

    if (!matched_collectible.empty()) {
        LogInfo << "========================================";
        LogInfo << "[JieGarden TestStrategy] Rare collectible ｢" << matched_collectible << "｣ detected!";
        LogInfo << "[JieGarden TestStrategy] Sending Slack webhook notification...";
        LogInfo << "========================================";

        std::string webhook_url = get_slack_webhook_url();
        if (!webhook_url.empty()) {
            std::string curl_cmd =
                "/usr/bin/curl -s --request POST --header 'Content-type: application/json' "
                "--data '{\"text\":\"發現稀有藏品: " +
                matched_collectible +
                "\"}' "
                "--location '" + webhook_url + "'";
            int ret = std::system(curl_cmd.c_str());
            LogInfo << "[JieGarden TestStrategy] Slack webhook sent, exit code:" << ret;
        }

        // 1. 完整退出游戏 (Force-stop Arknights game)
        LogInfo << "[JieGarden TestStrategy] Force-stopping Arknights game...";
        for (const auto& client : { "txwy", "Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR" }) {
            ctrler()->stop_game(client);
        }
        sleep(1000);

        // 2. 清空剩余肉鸽探索次数并终止任务
        LogInfo << "[JieGarden TestStrategy] Clearing remaining roguelike exploration count and terminating task...";
        if (auto process_ptr = dynamic_cast<ProcessTask*>(m_task_ptr)) {
            process_ptr->set_times_limit(m_config->get_theme() + "@Roguelike@StartExplore", 0);
            process_ptr->set_times_limit("Roguelike@StartExplore", 0);
        }
        if (m_task_ptr) {
            m_task_ptr->set_enable(false);
        }
        if (m_control_ptr) {
            m_control_ptr->set_enable(false);
        }
        return false;
    }

    return true;
}

} // namespace asst
