# project-skeleton：一次 `prepare` 之后的项目结构（合成样张）

这里是用**合成样张**跑 `prepare` 得到的项目骨架，可安全公开、不含任何真实个人信息。

```powershell
$NF = "$env:USERPROFILE\.dsh\native-forge\nf.cmd"
& $NF prepare --source '.\examples\project-skeleton\source.pdf' --pages 1-2 `
              --project '.\_demo\proj-skeleton' --title '合成示例项目'
```

`source.pdf` 是脚本生成的两页合成样张（标题、段落、公式、表格、图形占位），
`packet\pages\*.png` 是每页的渲染图（真实项目里每页 100–250 KB）。

| 文件 | 是什么 |
|---|---|
| `source.pdf` | 合成样张原稿（只读来源；真实项目换成你的原书 PDF） |
| `project.json` | 项目事实边界：来源 SHA256、页码范围、模板哈希、状态 |
| `content.json` | 正文内容（此时是空骨架，等 worker 按 `references\worker-contract.md` 填） |
| `assets.json` | 图资产登记表（此时为空） |
| `packet\packet.json` | 证据包索引（含每页 JSON/PNG 的哈希） |
| `packet\pages\pNNNN.json` | 单页抽取结果：文本块、bbox、页码 |
| `packet\pages\pNNNN.png` | 单页渲染图（识别与核验用，不作为出版正文） |

**注意**：

- 本目录是**结构样例，不能直接 `build`**：`content.json` 是空骨架，且 `project.json` 里的模板路径写成
  `<native-forge>/templates/...` 占位符（真实 `prepare` 会把本机引擎模板的绝对路径与哈希写进去）。
- `project.json` 的 `source.path` 写成相对路径 `source.pdf`；真实 `prepare` 会记录原稿的绝对路径与 SHA256。
- 想看真实产物形状，直接对任意小 PDF 跑一遍 `prepare`（见根 README「装完自检」），不要把这里的占位值照抄进自己的项目。
