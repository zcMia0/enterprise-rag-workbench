# 推送到 GitHub（已完成，此文档记录当前状态与后续操作）

> 仓库地址：https://github.com/zcMia0/enterprise-rag-workbench
> 远程分支 `main`，本地分支已统一为 `main`，两者已建立上游映射。

## 当前状态

代码已全部推送到远程，本地与远程一致。以后改完代码只需两条命令：

```bash
git add -A
git commit -m "说明改动"
git push          # 裸命令即可，上游映射已配好
```

推送凭据由 **Git Credential Manager**（版本 2.9.0，随 Git for Windows 安装）托管，
首次推送时通过浏览器授权，之后自动复用，**不需要把 token 写进任何文件或环境变量**。

## 仓库配置（已就位，无需重做）

| 项 | 值 |
| --- | --- |
| 远程地址 | `https://github.com/zcMia0/enterprise-rag-workbench.git` |
| 本地分支 | `main` |
| 远程分支 | `main` |
| 上游映射 | `branch.main.remote=origin` ／ `branch.main.merge=refs/heads/main` |
| 抓取规则 | `+refs/heads/*:refs/remotes/origin/*` |

## 历史说明

远程原有 4 个提交（仓库初始化 → 初版 → models.py 行尾修正 → README 网页编辑），
与本地开发历史没有共同祖先。已用 `git merge --allow-unrelated-histories` 合并为一个
合并提交，**远程那 4 个提交全部保留在历史里**，本地实现接在其后。

因为合并后远程 `main` 是本地 `main` 的祖先，推送是**快进（fast-forward）**，全程没有强推，
没有覆盖任何远程提交。

## 推送前安全自检

```bash
# 必须只有 .env.example，绝不能出现 .env / venv / node_modules / dist / uploads / data
git ls-files | grep -E '\.env$|venv/|node_modules/|/dist/|uploads/|/data/' || echo "OK: 无密钥与运行时产物"
```

当前 153 个被跟踪文件全部通过该检查。

## 备用通道：网络受限时走 REST API

若某天 `git push` 因网络策略失败（git 传输走 `github.com:443` 被拦或返回 502），
而 `api.github.com` 仍可访问，可用脚本经 Git Data REST API 推送：

```bash
# token 只从环境变量读取，脚本不写盘
GH_TOKEN=<你的 token> python scripts/push_via_api.py --repo zcMia0/enterprise-rag-workbench --branch main
```

注意该脚本是**整棵树重建提交**（blobs → tree → commit → ref），生成的 commit SHA
与本地提交不同，用于兜底应急；正常情况下优先用 `git push`，历史才是连续的。

## 曾经踩过的两个坑（已修，记录以免复发）

1. **抓取规则缺失**：远程抓取只落到 `FETCH_HEAD`，`origin/main` 引用建不出来，
   导致 `git fetch origin main` 后仍无法比较。已把 `remote.origin.fetch` 补成标准全局规则。
2. **本地与远程分支名不一致**：本地原为 `master`、远程为 `main`，`git fetch origin master`
   会报 `couldn't find remote ref master`，`git push` 也会要求显式写 `HEAD:main`。
   已把本地分支改名为 `main`，命名统一。
