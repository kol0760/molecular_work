# Molecular Workbench

个人分子网页工作台：React/TypeScript + 本地打包的3Dmol.js + FastAPI/SQLite + 真实GFN2-xTB。支持XYZ导入、三维查看／选择、坐标编辑、测量、撤销重做、多结构标签、单点能／优化、日志、历史与结果导出。无需运行时CDN。

这是**源码＋已构建前端**分发包，不是自带Python/xTB的免安装二进制，也不是离线安装包。包内不含账号、SSH密钥、用户结构、历史数据库、日志或本机环境。内置水和公开咖啡因示例属于应用示例，不是用户数据。

## Linux 启动

前提：Linux、Python3.10+（含venv/pip）、已安装的**xTB6.6.1**。前端已构建，普通使用无需Node/npm。后端使用Linux进程组、fcntl锁、资源限制和父进程退出保护。

1. 下载源码ZIP，解压到自己拥有的目录。建议Linux本地文件系统。
2. 安装xTB6.6.1并确保Linux终端运行 `xtb --version` 可识别；或设置绝对路径 `WORKBENCH_XTB`。xTB单独安装，不随本包分发。官方安装说明：https://xtb-docs.readthedocs.io/en/latest/setup.html 。安装时务必检查实际版本，其他版本暂不接受科学结果。
3. 终端进入项目目录：

```bash
bash start-linux.sh
```

首次启动会创建项目`.venv`并从包索引下载锁定的Python依赖，不修改系统Python环境。需要联网。后续使用相同命令启动。打开 **http://127.0.0.1:8765**，Ctrl+C停止。保持终端开启；没有自动后台／开机启动。

检查而不安装、不启动：

```bash
python3 tools/portable.py check
# 只初始化空白配置，永不覆盖已有配置
python3 tools/init_config.py
```

若xTB不在PATH，初始化后编辑`.private/local.json`的`xtb_executable`为**本机Linux绝对路径**。文件须0600、目录0700。配置只由管理员读取，API不能更改执行程序。也可在启动前设置环境变量：

```bash
export WORKBENCH_XTB="/opt/xtb/bin/xtb"
bash start-linux.sh
```

该路径是示例，不代表你的实际安装位置。若8765已被其他应用占用，启动会失败；不会终止其他进程。不要同时启动两个实例。

## Windows 启动：WSL2 路线

**不支持原生Windows Python后端**；Windows使用WSL2内的Linux后端，网页在Windows浏览器打开。Windows10/11的实际版本和虚拟化能力须满足微软WSL2要求。

1. 按[微软WSL安装文档](https://learn.microsoft.com/windows/wsl/install)安装WSL2及Linux发行版。必要时重启；这些系统操作由你自行完成，本项目不会自动修改Windows功能。
2. 在WSL发行版内安装Python3.10+及venv/pip、xTB6.6.1。Windows原生的Python/xTB不能替代WSL内依赖。
3. 解压项目后双击 **Start-Windows.cmd**。它只调用默认WSL发行版中的`start-linux.sh`。如果命令行窗口提示缺少依赖，按提示先在WSL内完成安装。
4. Windows浏览器打开 **http://localhost:8765**。WSL的localhost转发取决于Windows/WSL配置；若不可用，先在WSL内验证Linux本机访问，不要直接扩大监听范围或关闭安全检查。

推荐把项目放在WSL Linux文件系统；可在WSL终端进入项目后运行 `bash start-linux.sh`。Windows入口用`wsl.exe --cd`定位项目目录，不会安装WSL或创建凭据。此入口经过静态检查，**尚未在真实Windows/WSL2机器验收**。

## Slurm 怎么设置

当前Slurm只是**管理员使用的默认禁用适配器**，不在网页计算菜单中。填写配置不会把Slurm暴露到网页；现有网页没有多用户授权，不能直接接到集群。

```bash
python3 tools/init_config.py
# 用本地编辑器编辑 .private/slurm.json，暂时保留 enabled:false
python3 tools/check_slurm.py
```

| 配置项 | 本地填写内容 |
|---|---|
| `enabled` | 默认false；真实集群验收前保持关闭 |
| `ssh_host_alias` | 你自己SSH客户端配置中的主机别名；不是密码 |
| `remote_work_root` | 远端专用绝对目录，自己所有、0700，目录已存在 |
| `partition` / `account` | 集群分区／计费账号；允许默认时可留空 |
| `cpus` | 每任务CPU数1–128；按集群规则选择 |
| `memory_mb` | 内存MiB，128–262144 |
| `time_minutes` | 时间上限1–1440分钟 |
| `xtb_executable` | 远端xTB6.6.1绝对路径 |
| `environment_setup` | 管理员审核的模块加载／环境激活Bash；必须明确填写 |
| `site_preamble` | 可选站点前置Bash，默认空 |

配置文件0600；不要把密码、私钥或令牌写进去／提交Git。`environment_setup`与`site_preamble`属于可信管理员脚本，会写到远端私有作业文件；不要放秘密。SSH连接由操作系统管理，项目不生成、不收集凭据。端点必须已有可信known_hosts记录，适配器拒绝交互登录和自动接受主机密钥。

模板见`templates/slurm.sbatch.in`；CPU、内存、时间、作业名和工作目录作为固定sbatch参数生成。详细限制、代码调用与启用前必做的真实测试见[Slurm说明](docs/slurm.md)。没有配置时输出“Not connected”，不会执行SSH/Slurm。模拟测试通过不等于真实集群可用。

## 安全和科学边界

默认只监听127.0.0.1:8765，Host/Origin限本机；无公网入口、隧道或远程发布代码。保持JSON、X-Workbench、Fetch Metadata跨站写入保护。不要把本程序直接监听公网。原子视觉连线为推断键，优化收敛不代表全局最低能。

本机队列一次一个计算，一线程、600秒、2GiB、20MiB文件上限、最多20个排队任务；输入最大300原子和128KiB。参数固定GFN2、气相，科学成功要求实际6.6.1版本、SCC明确收敛、有限能量；优化另需几何收敛和对应有效结构。状态未知／不收敛不算成功。重启不会自动重跑未完成任务。

## 开发和测试

```bash
# 在setup创建的环境里，实引擎测试要求PATH/WORKBENCH_XTB指向xTB6.6.1
.venv/bin/python -m pytest -q
# 重建前端：需要Node22+及npm，可联网下载开发依赖
cd frontend
npm ci
npm run build
node unit/model.test.mjs
# 浏览器测试仅开发用：另安装Playwright Chromium并先启动本机应用
npx playwright install chromium
npx playwright test
```

源码保留了测试；依赖历史运行日志的3个重放测试明确跳过，日志不分发。实引擎CLI比较测试在临时目录重新产生公开水分子结果。

## 第三方和授权说明

不打包Python、xTB、SSH、WSL或任何第三方可执行运行时。已构建前端包含React、ReactDOM、Scheduler与3Dmol.js；原始许可证保留于`THIRD_PARTY_LICENSES/`。其他依赖按各自许可证使用。项目自己的源码未额外授予开源许可证；GitHub公开可见不等于授予任意再许可权。不要将第三方库、参考网站的品牌／内容或运行时的授权误认为本项目可自行重新授权。详见[第三方说明](THIRD_PARTY_NOTICES.md)。

可选本机端口：`WORKBENCH_PORT=18765 bash start-linux.sh`，只改变回环端口，不开放公网。验证细节和未运行检查见[验证说明](docs/VALIDATION.md)。
