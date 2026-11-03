# 推送到 GitHub 指南（本仓库已本地提交，待你执行推送）

> 沙箱环境无法连通 github.com（`curl` 超时）且未安装 `gh` CLI，因此**实际推送需在你的本机终端完成**（网络 + 你的 GitHub 凭据都在本机）。
> 下方命令直接复制粘贴即可，把 `<你的GitHub用户名>` 换成真实用户名。

## 方式 A（推荐）：网页建仓 + 本机推送

1. 打开 https://github.com/new
2. Repository name 填：`enterprise-rag-workbench`
3. **不要**勾选 "Add a README file" / "Add .gitignore"（仓库已有）
4. 点 **Create repository**
5. 在本机该目录执行：

```bash
cd enterprise-rag-workbench
git remote add origin https://github.com/<你的GitHub用户名>/enterprise-rag-workbench.git
git branch -M master
git push -u origin master
```

## 方式 B：用 GitHub CLI（`gh`）一键建仓并推送

本机先安装并登录 `gh`（Windows：`winget install GitHub.cli` 或 https://cli.github.com ）：

```bash
gh auth login
cd enterprise-rag-workbench
git branch -M master
gh repo create enterprise-rag-workbench --private --source=. --remote=origin --push
```

## 方式 C：已建好空仓库，仅补 remote + 推送

```bash
cd enterprise-rag-workbench
git remote add origin https://github.com/<你的GitHub用户名>/enterprise-rag-workbench.git
git push -u origin master
```

## 推送前自检（安全红线）

```bash
# 必须只有 .env.example，绝不能出现 .env / venv / node_modules / dist / uploads / data
git ls-files | grep -E '\.env$|venv/|node_modules/|/dist/|uploads/|/data/' || echo "OK: 无密钥与运行时产物"
```

## 推送后

- 仓库地址即：`https://github.com/<你的GitHub用户名>/enterprise-rag-workbench`
- 本地启动方式见 `README.md`「快速开始」。
