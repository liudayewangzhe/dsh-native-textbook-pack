# 先规划、试排，再扩量

`scripts/plan_document.py` 用于建立和检查项目内 `layout-plan.json`。它使“证据 → 决定 → 实际样页试排 → 放行”的缺项可见，避免 worker 根据候选数量猜版式。它不调用模型、构建、OCR、外链或证据中的命令。

`plan_ready` **不等于内容或美观验收**。检查器只核对结构、路径、哈希、页码和待办，无法判断一句观察是否真实，也不会取代现有 build/qa/release 及人工看图。不能靠填写“reviewed/通过/完成”三个字取得放行。

## 两个命令

在引擎根目录、带 PyMuPDF 的 Python 环境执行。前检须为 `preflight_pdf.py` 生成的完整单书报告，不能传 corpus 汇总。

```powershell
python scripts/plan_document.py scaffold --preflight reports/source-preflight/book-a.json --project projects/book-a
python scripts/plan_document.py check --project projects/book-a
```

scaffold 将前检复制到项目 `planning/preflight.json` 并绑定其 SHA-256；只从前检取来源身份、页数和未确认候选，不打开或渲染原书。它不覆盖现有计划，也不覆盖内容不同的前检缓存。新建计划始终待定，决定为空、pilot 为 pending，首次 check 应当失败。

已有草稿或书稿补登记规划时，必须如实标明回填身份：

```powershell
python scripts/plan_document.py scaffold --preflight projects/book-a/audit/preflight/book-a.json --project projects/book-a --retrospective
```

这会写 `planning_mode:retrospective` 与当前 UTC 创建时间，不能称作生成前已经完成的规划。项目已经存在 `build/main.pdf` 而未给此标志时拒绝创建。新项目缺省 `planning_mode:prospective`。

scaffold 成功退出 0，但输出 `plan_ready:false`。check 通过退出 0，缺项、过期或不合法退出 2，均输出 JSON。check 只读文件，不写通过状态；更改材料后必须重跑。

## 文件与字段

文件引用统一为 `{"path":"项目内相对路径","sha256":"该文件的64位小写SHA-256"}`。证据另加 `role`；样张证据必须同时有 `render` 和 `review`。render 文件须有 PNG、JPEG 或 PDF 签名，review 可以是实际观察报告。不得拿只有“已检查”的空泛声明充当观察。文件存在与哈希一致只证明材料已提供且内容未变，不证明材料支持描述。

除只读 `source.path` 为原稿绝对路径外，所有引用都在项目内，解析 `..` 和符号链接后仍不得越界；空文件、缺失路径和过期哈希会失败。全局 worker 合同可复制相关内容为项目内任务单，再引用它的当前哈希。脚本只读这些材料，不执行脚本、宏或外部指令。

| 字段 | 要填什么 |
|---|---|
| `schema_version`、`planning_mode`、`created_at` | scaffold 生成的版本、前置/回填身份、创建时间 |
| `source` | 原稿 `path/sha256/page_count`；check 重算来源哈希 |
| `preflight` | 当前项目内前检文件引用；须和来源路径、哈希、页数一致，且包含全部逐页记录 |
| `candidate_summary` | 未确认线索备忘，不是已识别事实，不自动决定对象路线 |
| `geometry` | `decision/reason/evidence`；另选已有 `profile:legacy-a4`，或 `layout_config` 文件引用 |
| `content_routes` | 每项 `kind/decision/reason/evidence`；写本书实际涉及的正文、数学、图表、代码等路线，不填写不存在的类别来凑数量 |
| `risk_cases` | 真实问题及样页记录，结构见下；不从候选自动创建“真风险” |
| `risk_review_reason` | 无需特殊风险样张而 `risk_cases:[]` 时解释理由；正常正文样张仍必须完成 |
| `pilot` | `status/build/build_record/sample_source_pages/sample_output_pages/evidence/findings/reviewer/unresolved` |
| `worker_contract` | 项目内实际 worker 任务单引用，含范围、允许写入和保留约束 |
| `unresolved` | 未决项列表；任何未决项阻止放行，确实不适用可按下述形式说明 |

`geometry.profile:legacy-a4` 指现有默认 A4（210×297 mm、正文 164 mm、左右各 23 mm）；使用它时 `layout_config:null`。不是本书默认就不要套用。自定义方案用 `profile:null`，`layout_config` 指向含 `layout` 的实际 JSON，例如当前 `project.json`。其中须明确 `paper_width_mm/paper_height_mm/text_width_mm` 的有限正数；其他现有 layout 字段保留。检查器不再复制完整几何 schema，尺寸闭合、注栏位置等仍由构建/QA 和实际页面验证。“合理加宽”不是配置。

`pilot.build` 引用实际样张 PDF，`build_record` 引用该构建的 `build/fingerprint.json`。检查器只核对其中 `files.source/files.pdf` 与当前来源和 PDF 哈希一致，并读取 PDF 页数以检查样页范围；它不重新实现引擎完整指纹新鲜度校验。样张必须由使用中的引擎构建并按现有流程通过技术检查，不能手工捏造构建记录。

`sample_source_pages` 使用原 PDF 物理页码，`sample_output_pages` 使用样张输出 PDF 页码。两者不需要相同，均须为非空、唯一且不越界的整数数组。样张须包含正常正文，以便判断阅读行长和节奏；这件事由监工看图确认，脚本不靠文字标签推断。`status:passed` 还必须有具体 `findings`、reviewer、真实渲染与复核材料，不能只填状态词。

## 风险和“不适用”

风险项采用以下形状，示例中的文件引用和说明必须用实际材料填写，不能原样照抄为已验证：

```json
{
  "id": "wide-derivation",
  "source_page": 24,
  "evidence": [{"path": "audit/source-page-24.png", "sha256": "实际文件哈希", "role": "source"}],
  "problem": "源页中的连续推导超出拟用正文栏，需核对拆行和编号归属。",
  "decision": "按等号关系拆行；不足时使用实际试验过的 full 跨度。",
  "validation": {
    "status": "pending",
    "build_sha256": "",
    "pilot_pages": [],
    "evidence": [],
    "findings": ""
  }
}
```

通过时 validation 必须有当前 pilot PDF 哈希、合法输出页码、render/review 两类材料和具体观察。风险的源页及输出页还必须分别包含在 pilot 的样页清单中。页数与风险数量由实际内容决定，不设置固定配额；简单文章允许空风险表，但需要 `risk_review_reason` 和正常页面试排证据。

未决项不能改名为“通过”来绕过。确实不存在/不适用时可以记录：

```json
{
  "item": "二维码解码",
  "status": "not_applicable",
  "reason": "已看所选源页只有普通照片与图标，没有确认的二维码对象。"
}
```

检查器接受这种显式说明，不要求为了过关制造一个二维码风险；说明是否成立仍由监工承担。存在但未核对的对象不能写 not_applicable。

## 少返工的使用方式

先让受限 worker 只整理已有候选、填待确认问题和提出局部路线，监工看原页后作决定。只试排受影响的完整小节，失败时保留证据和错误原因，只修改有关配置或对象；更改 PDF 后更新当前 hash 并重新核对该样张。通过后给批量 worker 对应路线、来源范围、已验证样张和不变约束，不反复发送全书所有页面和全部通用规则。

对现有《金融物理》完成的多轮精排补任务单，是 `retrospective` 验证案例，不证明新初稿在规划后生成。本工具也不承诺减少多少 token；收益须以实际返工减少和结果质量衡量。

回归测试为 `tests/test_document_plan.py`，涵盖待定脚手架、简单文档无虚构风险、来源/前检/证据过期、越界路径/页码、状态词伪通过、缺失渲染材料、实际配置、构建绑定、不适用与回填身份。此模块不修改主引擎、模板或指纹文件。
