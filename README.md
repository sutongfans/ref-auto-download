# HuggingFace Daily Papers Scraper

这个项目是一个自动化工具，用于每日定时抓取HuggingFace上的论文，下载PDF文件，并通过MCP服务进行处理。

## 项目结构

```
huggingface_scraper/
├── 📂 downloaded_papers/     # 下载的论文存储目录
├── 📂 logs/                  # 日志文件目录
├── 📂 state/                 # 状态文件存储目录
├── 📂 mcp/                   # MCP模块 - AI处理服务
│   ├── 📜 server.py          # API服务器的核心代码
│   ├── 📜 model_loader.py    # 加载模型的代码
│   ├── 📜 requirements.txt   # MCP模块专属的依赖
│   └── 📜 Dockerfile         # MCP服务的Docker配置
├── 📜 config.ini             # 配置文件
├── 📜 downloader.py          # 爬取和下载论文的模块
├── 📜 processor.py           # 处理PDF和与MCP服务交互的模块
├── 📜 main.py                # 主入口和定时任务
├── 📜 requirements.txt       # 项目依赖
├── 📜 docker-compose.yml     # Docker Compose配置
└── 📜 README.md              # 项目说明文档
```

## 功能特点

1. **定时抓取**：通过Cron定时任务触发`main.py`，每日自动抓取HuggingFace上的论文。
2. **自动下载**：`downloader.py`爬取并下载PDF到按日期组织的目录（`downloaded_papers/YYYY-MM-DD/`）。
3. **实时处理**：`processor.py`后台运行，使用watchdog监控新下载的PDF文件。
4. **AI处理**：检测到新PDF后，将其发送给MCP服务进行处理。
5. **Docker支持**：MCP服务在Docker中后台运行，接收请求并处理PDF。
6. **结果输出**：处理结果以JSON格式返回，并打印到标准输出，方便其他下游平台使用。
7. **完善的日志**：详细记录每一步的执行状态，包括成功和失败的情况。

## 安装与配置

### 前提条件

- Python 3.8+
- Docker和Docker Compose（用于运行MCP服务）
- Cron（用于定时任务）

### 安装步骤

1. 克隆项目并安装依赖：

```bash
# 安装主项目依赖
pip install -r requirements.txt

# 安装MCP模块依赖（可选，如果不使用Docker）
pip install -r mcp/requirements.txt
```

2. 配置`config.ini`文件：

```ini
# 根据需要修改配置参数
[scheduler]
daily_run_time = 00:00  # 每日运行时间
```

3. 启动MCP服务（使用Docker）：

```bash
docker-compose up -d
```

4. 设置Cron定时任务：

```bash
# 编辑crontab
crontab -e

# 添加以下内容（每天00:00运行）
0 0 * * * cd /path/to/huggingface_scraper && python main.py
```

## 使用方法

### 手动运行

1. 运行主程序：

```bash
python main.py
```

2. 单独运行下载器：

```bash
python downloader.py
```

3. 单独运行处理器：

```bash
python processor.py
```

### 查看日志

日志文件存储在`logs/`目录下，按日期命名：

```bash
cat logs/scraper_YYYYMMDD.log  # 查看主程序日志
cat logs/processor_YYYYMMDD.log  # 查看处理器日志
```

## 扩展与自定义

### 添加AI模型

要添加实际的AI模型处理能力，修改`mcp/model_loader.py`文件：

1. 安装所需的AI模型库（如transformers、torch等）
2. 在`_load_model`方法中实现模型加载逻辑
3. 在`process_pdf`方法中实现PDF处理逻辑

### 自定义爬取逻辑

如果HuggingFace网站结构发生变化，可以修改`downloader.py`中的`_fetch_paper_list`方法来适应新的HTML结构。

## 故障排除

- **MCP服务无法连接**：检查Docker容器是否正常运行，端口是否正确映射。
- **PDF下载失败**：检查网络连接和HuggingFace网站是否可访问。
- **处理器未检测到新文件**：确保watchdog正常运行，检查文件权限。

## 许可证

[MIT License](LICENSE)
