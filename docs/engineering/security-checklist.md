# Security Checklist

---

## 提交前检查

- [ ] 代码中无硬编码 API Key、Token、Cookie、密码
- [ ] `.env`、`.env.local`、数据库文件未被追踪
- [ ] `.env.example` 只包含占位符
- [ ] 日志中不打印敏感信息
- [ ] CORS 不使用 `allow_origins=["*"]`
- [ ] 不抓取付费内容、私密内容、非用户本人可访问内容

## 推荐命令

```bash
# 检查 Git 状态
git status

# 确认敏感文件未被追踪
git ls-files | grep -E "\.env$|\.env\.|\.db$|\.sqlite3$"

# 扫描硬编码密钥
grep -rn --include="*.py" --include="*.ts" --include="*.tsx" \
  -E "(api_key|secret|token|password|cookie)\s*[:=]\s*[\"'][^\"']{10,}" .
```

Windows 环境可用 PowerShell 或 findstr 等价命令。

## Cookie / 登录态边界

禁止抓取付费内容、私密内容、非用户本人可正常访问的内容。

Cookie / 登录态仅允许用于用户本人账号在浏览器中可正常访问的公开或半公开页面检索，不绕过权限、不破解、不批量导出私密数据。

登录态失效时必须降级为该来源不可用，并记录结构化 warning，不允许绕过验证。

---

## 变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-06-12 | 初始版本 |
