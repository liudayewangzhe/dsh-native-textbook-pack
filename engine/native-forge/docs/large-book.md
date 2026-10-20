# 长书、并行与恢复

`project.json` 是整本书的统一来源和授权页码。先按目录划分章节，再在长章节里选择保持论证完整的小节作为 worker 任务，不按字符上限机械切断公式、证明和表格。

每个 worker 只读本任务页及必要的相邻页上下文，只写 `chunks/有序编号.json`。所有 worker 使用相同术语表和数学宏；asset ID 使用原图编号或书内唯一名称。不要并发改共享 content.json、assets.json 或模板。图形资源由监工分配唯一名称并登记。章节边界的一页有时包含两节，允许两个 chunk 使用同一来源证据块，但必须在 source_notes 指出精确片段，不能由覆盖 ID 掩盖遗漏。

读取完整授权范围的 packet 后，监工按阅读顺序合并：

```powershell
& 'C:\Users\ltllt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  'E:\PDF\_ZH\native-forge\scripts\merge_chunks.py' `
  --project '项目目录' --chunks '项目目录\chunks\001.json' '项目目录\chunks\002.json'
```

合并器为内容 ID 加 chunk 前缀，保留原书公式/图表号，合并来源期望和未解决项。重复页眉排除可去重；某个小节暂时排除的范围外块，如果由另一个小节纳入，则撤销该局部排除并记入 merge-ledger.json。任何真正缺失、未解决、冲突或标签重复都阻止替换当前稿。合并通过仍须编译、对照原稿并逐页看成品。

已经成功的 chunk、packet 和资产落盘复用；失败只重做该小节或对象。定稿后再编译整本书，完整复核清单才能发布。大书可先逐章编译校对，整书编译不能替代章节的语义复核。不要把样例的阅读/生成时间线性放大成未经测量的全书耗时承诺。

扫描页若无可用文本块，需监工根据页面写逐对象清单与来源区域；机器的空文本覆盖不能证明扫描页已经完整还原。不得将整页位图登记为“照片”而发布。应先在包含密集公式与图表的扫描小节验证识别和复核方法，再扩展到用户授权范围。
