# Native Forge 工作区规则

- 出版主表示为 content.json 的语义 TeX。来源页 PNG 是只读核验材料，公式和表格不能截图回退。
- 使用已安装的 native-textbook 技能；主引擎和模板不因单页问题随意改写。一般内容问题改项目中的具体块；实际通用问题才修引擎并跑相应测试。
- DeepSeek 可做边界明确的批量翻译、TeX和机械检查；读目录、写目录必须限定到任务。Codex 对照来源验收。
- 先保持范围、完整内容及来源事实，再优化排版。源书错误不能默默改正；明确译注或用户授权的更正须留下记录。
- 分派多个小节时只写各自 chunk，监工合并；共享 content.json、assets.json、模板不并发修改。
- build/qa 不等于 release；不能替未做的源文校对或页面检查填写通过。
- 原稿与旧 BookForge 只读保留；所有新工作在此目录的 projects/reports 下。
- 本地空闲物理内存低于1GiB暂停重工作，保护Codex、Elephant、VPN、SSH及系统进程，不终止它们。
