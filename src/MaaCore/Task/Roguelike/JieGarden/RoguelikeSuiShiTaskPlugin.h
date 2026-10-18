#pragma once

#include "Common/AsstTypes.h"
#include "Task/Roguelike/AbstractRoguelikeTaskPlugin.h"

#include <string>

namespace cv
{
class Mat;
}

namespace asst
{

class RoguelikeSuiShiTaskPlugin : public AbstractRoguelikeTaskPlugin
{
public:
    using AbstractRoguelikeTaskPlugin::AbstractRoguelikeTaskPlugin;
    virtual ~RoguelikeSuiShiTaskPlugin() override = default;

    virtual bool verify(AsstMsg msg, const json::value& details) const override;
    virtual void reset_in_run_variables() override;

protected:
    virtual bool _run() override;

private:
    std::string detect_suishi_from_image(const cv::Mat& image) const;
    bool log_yitrader_goods();

private:
    mutable std::string m_saved_suishi;
    mutable std::string m_current_task;
};

} // namespace asst
