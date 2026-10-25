# fixedwidth-transit

按**字节宽度**在定长文件与 UTF-8 CSV 之间双向转换，适用于有明确字段布局的批量数据交接。
使用 Python 3.11+ 标准库，无运行时第三方依赖、网络访问或类型推断，MIT 许可证。

克隆仓库后创建并激活虚拟环境，运行 `python -m pip install .`。示例：

```sh
fixedwidth-transit encode examples/people.csv --layout examples/layout.json --output people.dat
fixedwidth-transit decode people.dat --layout examples/layout.json --output roundtrip.csv
```

两步均应退出 0、报告 2 条记录。每条记录为 20 字节加换行符；`東京` 是 6 个 UTF-8 字节。
示例结束删除自己生成的两个文件。卸载：`python -m pip uninstall fixedwidth-transit`。
也可从 Release 安装 wheel；尚未发布到 PyPI。

布局字段顺序决定字节偏移。`padding` 可选 `left`、`right`（默认）和 `none`；
`pad` 默认为空格。解码去除声明侧的填充，编码补回；输入值若在该侧自带填充字符则拒绝，
避免歧义。有意义的尾部空格应使用 `none`，此时必须恰好占满字段字节宽度。

支持 UTF-8、ASCII、Latin-1、CP1252、Shift-JIS、CP932；分隔符支持 LF、CRLF 或无分隔符。
禁止截断、非法字符、编码往返改变、字段内 CR/LF/NUL、重复字段、列数不一致。
CSV 表头必须与布局完全一致。定长输入最后一条可无换行，输出统一添加配置的分隔符。

输出先在同目录临时文件中构建，完全成功后才发布。默认不覆盖（需要支持硬链接的文件系统），
`--force` 只在成功后替换；失败保留旧输出，不可覆盖输入或布局文件。请使用静态输入和可信目录。
退出 2 表示错误，诊断不回显数据值。中断可能留下 `.transit-*.tmp`，仅清理自己任务的临时文件。

v0.1.1 限制：布局 64 KiB、每条记录与 CSV 单字段 1 MiB、最多 1024 列；
不支持 EBCDIC、UTF-16、COBOL、压缩文件、混合记录、自动推断、远端 URL 或 stdin。
不会保留 CSV 原始引号风格，也不会过滤电子表格公式。完整语义及开发测试见英文 README。
