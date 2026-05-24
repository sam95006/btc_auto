# Binance「模擬交易 → U 本位合約」API 官方文件與申請指南

> 對應 NEXUS 環境變數：`BINANCE_FUTURES_TESTNET_API_KEY` / `SECRET`  
> API 網址：`BINANCE_FUTURES_BASE_URL=https://demo-fapi.binance.com`  
> **不含幣本位**（幣本位走 dapi，本專案未接入）

---

## 一、先分清三種「模擬」環境（不要搞混）

| 名稱 | 用途 | REST API | 在哪申請 API Key |
|------|------|----------|------------------|
| **U 本位合約 Testnet / Demo** | 合約模擬（你 App 的 U 本位分頁） | `https://demo-fapi.binance.com` | [Futures Testnet 網站](https://testnet.binancefuture.com/) |
| **現貨 Demo Mode** | 現貨模擬（App「模擬交易→現貨」） | `https://demo-api.binance.com` | [demo.binance.com API 管理](https://demo.binance.com/en/my/settings/api-management) |
| **現貨 Testnet** | 舊版現貨測試網 | `https://testnet.binance.vision/api` | [testnet.binance.vision](https://testnet.binance.vision/) |
| **幣本位合約**（不要用） | App「幣本位合約」分頁 | `dapi` / 另一套 | 勿與 U 本位混用 |

NEXUS 合約端只接 **U 本位 demo-fapi**。

---

## 二、官方開發者文件（必讀）

### U 本位合約（USDⓈ-M / USDT-M）

| 說明 | 連結 |
|------|------|
| 基本信息（含 Testnet URL）**中文** | https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/general-info |
| General Info **英文** | https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info |
| 衍生品快速開始 | https://developers.binance.com/docs/derivatives/quick-start |
| 更新日志（接口变更） | https://developers.binance.com/docs/zh-CN/derivatives/change-log |
| 账户接口 V2（查保證金餘額） | https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2 |
| 下单测试（不真正成交） | https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order-Test |
| Postman 集合 | https://github.com/binance/binance-api-postman |

**Testnet 重點（官方原文）：**

- REST：`https://demo-fapi.binance.com`
- WebSocket：`wss://fstream.binancefuture.com`

### 現貨 Demo（若也要對 App 現貨分頁）

| 說明 | 連結 |
|------|------|
| Demo Mode 说明 | https://developers.binance.com/docs/binance-spot-api-docs/demo-mode/general-info |
| Demo API 管理页 | https://demo.binance.com/en/my/settings/api-management |
| 现货 Testnet | https://testnet.binance.vision/ |

### 幣本位（僅供對照，NEXUS 不用）

| 說明 | 連結 |
|------|------|
| 币本位合约基本信息 | https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/general-info |

---

## 三、如何申請「U 本位合約」模擬 API Key（實操）

官方寫法：Futures Testnet **目前主要透過 API / 測試網站** 使用（見 [Quick Start - Futures Testnet](https://developers.binance.com/docs/derivatives/quick-start)）。

### 步驟 A：註冊 / 登入 Futures Testnet

1. 瀏覽器開啟：**https://testnet.binancefuture.com/**
2. 可用 GitHub / Google / 郵箱註冊（與主站帳號分開的測試環境）
3. 登入後進入交易介面（例如 BTCUSDT）

### 步驟 B：建立 API Key

1. 在交易頁下方分頁找到 **「API Key」**（與 Positions、Open Orders 等並列）
2. 建立 **HMAC** 類型金鑰（程式交易用）
3. 建議勾選：**讀取** + **合約交易**（依你需求）
4. 可設 IP 白名單（Zeabur 動態 IP 可先不綁，或之後再改）

參考教學（非官方，僅輔助）：

- https://tradeadapter.com/binance_create_api_key_futures_demo

### 步驟 C：對齊你手機 App「U 本位」餘額

手機 **模擬交易 → 合約 → U 本位合約** 的保證金餘額，必須與 **同一個 demo 帳戶** 的 API 一致。

若 `python tools/deploy/diagnose_binance_balances.py` 的 `futures_equity` 與 App 的 **保證金餘額** 不同：

- 代表 Zeabur / `.env` 的合約金鑰 **不是** App 那個帳戶
- 請在 **顯示 9277 的那個模擬帳戶** 對應的 Testnet / Demo 後台重新產生金鑰

### 步驟 D：寫入 NEXUS / Zeabur

```env
BINANCE_FUTURES_TESTNET_API_KEY=你的Key
BINANCE_FUTURES_TESTNET_SECRET_KEY=你的Secret
BINANCE_FUTURES_BASE_URL=https://demo-fapi.binance.com
NEXUS_FUTURES_SCOPE=usdt_m
NEXUS_INCLUDE_COIN_MARGINED=0
```

現貨模擬（另兩把，與合約分開）：

```env
BINANCE_SPOT_TESTNET_API_KEY=...
BINANCE_SPOT_TESTNET_SECRET_KEY=...
# 預設 https://testnet.binance.vision/api
```

---

## 四、通用 API Key 說明（主站規則）

| 說明 | 連結 |
|------|------|
| 如何建立 API Key（主站 FAQ） | https://www.binance.com/zh-CN/support/faq/how-to-create-api-keys-on-binance-360002502072 |
| 英文版 | https://www.binance.com/en/support/faq/how-to-create-api-keys-on-binance-360002502072 |

注意：**主站 www.binance.com 產生的 API Key 是實盤**，不能用在 `demo-fapi.binance.com`。

---

## 五、驗證金鑰是否對到 U 本位（本專案）

```powershell
python tools/deploy/diagnose_binance_balances.py
```

對照輸出：

- `futures_base_url` 應含 `demo-fapi.binance.com`
- `futures_equity` ≈ App **U 本位 → 保證金餘額**
- 勿用 **幣本位合約** 分頁數字比對

Zeabur 部署後：

`GET https://你的網域/api/nexus/connectivity`

---

## 六、常見錯誤

| 現象 | 原因 |
|------|------|
| 餘額與 App 差很多 | 金鑰屬於另一個 testnet 帳戶；或現貨/合約用了不同帳戶的金鑰 |
| Invalid API-key | 把主站金鑰打到 demo-fapi；或 URL 用錯 |
| 看到幣本位數字被加進去 | 本專案不查 dapi；請確認比對的是 App **U 本位** 分頁 |

---

*整理日期：2026-05-22 · 以 Binance 官方開發者文檔為準*
