# 可恢复编排小样本

这是自有合成文本的调度验证，不是整书翻译，也不输出 PDF。它实际覆盖缺包阻断、断点复用、作用域术语修订、模板变化只重建，以及输出篡改阻断。不会调用模型或读取 API key。

从仓库根目录运行，输出路径必须尚不存在：

```powershell
python examples/orchestration_smoke.py --out '<新的临时目录>/orchestration-smoke'
```

查看生成的 `smoke-report.json`、`translation-manifest.json`、`run-state.json` 与 `state/briefs/`。布局修改后 `verify` 仍可证明草稿集合完整，但 `needs_rebuild:true`、`review_valid:false`，不能宣称已有合格 PDF。

完整单元与真实引擎集成回归：

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
```

`test_translation_state.py` 仅需标准库；`test_orchestration_integration.py` 需要项目现有 PyMuPDF，并用临时自有英文 PDF 执行真实 `prepare`、调度器和 `merge_chunks.py`。缺依赖时会明确跳过，不把跳过当通过。测试不填终审、不调用发布器。

实际项目先用 `nf.cmd prepare` 或相应来源适配建立证据，再按完整语义单元写 spec 和术语表；按 [translation-orchestration.md](../skills/native-textbook/references/translation-orchestration.md) 执行。`context_chars:0` 在本样例仅用于隔离术语选择性测试，不是长书推荐值。
